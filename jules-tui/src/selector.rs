//! Shared state for interactive selectors.
//!
//! `ActiveSelector` makes selector ownership explicit: the application can
//! render and route input to at most one interactive modal at a time.

use crate::sessions::SessionItem;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ActiveSelector {
    Themes,
    Models,
    Providers,
    Sessions,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SelectorState {
    pub selected: usize,
    pub query: String,
}

impl SelectorState {
    pub fn reset(&mut self) {
        self.selected = 0;
        self.query.clear();
    }

    pub fn move_selection(&mut self, delta: i32, len: usize) {
        if len == 0 {
            self.selected = 0;
            return;
        }

        let len = len as i32;
        self.selected = ((self.selected as i32 + delta).rem_euclid(len)) as usize;
    }

    pub fn clamp_selection(&mut self, len: usize) {
        self.selected = if len == 0 {
            0
        } else {
            self.selected.min(len - 1)
        };
    }

    pub fn set_query(&mut self, query: String) {
        self.query = query;
        self.selected = 0;
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SessionsStatus {
    Idle,
    Loading,
    Ready,
    Empty,
    LoadingSession,
    Deleting,
}

impl Default for SessionsStatus {
    fn default() -> Self {
        Self::Idle
    }
}

impl SessionsStatus {
    pub fn is_pending(self) -> bool {
        matches!(self, Self::Loading | Self::LoadingSession | Self::Deleting)
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SessionsSelectorState {
    pub selection: SelectorState,
    pub status: SessionsStatus,
    pub confirming_delete: Option<String>,
    pub feedback: Option<String>,
}

impl SessionsSelectorState {
    pub fn is_pending(&self) -> bool {
        self.status.is_pending()
    }

    pub fn begin_loading(&mut self) -> bool {
        if self.is_pending() {
            return false;
        }
        self.selection.reset();
        self.status = SessionsStatus::Loading;
        self.confirming_delete = None;
        self.feedback = Some("Loading sessions...".to_string());
        true
    }

    pub fn set_sessions(&mut self, sessions: &[SessionItem]) {
        self.selection
            .clamp_selection(self.filtered_indices(sessions).len());
        self.status = if sessions.is_empty() {
            SessionsStatus::Empty
        } else {
            SessionsStatus::Ready
        };
        self.feedback = None;
    }

    pub fn filtered_indices(&self, sessions: &[SessionItem]) -> Vec<usize> {
        let query = self.selection.query.trim().to_lowercase();
        sessions
            .iter()
            .enumerate()
            .filter_map(|(index, session)| {
                let matches = query.is_empty()
                    || session.title.to_lowercase().contains(&query)
                    || session.id.to_lowercase().contains(&query);
                matches.then_some(index)
            })
            .collect()
    }

    pub fn selected_session_id<'a>(&self, sessions: &'a [SessionItem]) -> Option<&'a str> {
        let index = *self
            .filtered_indices(sessions)
            .get(self.selection.selected)?;
        Some(sessions[index].id.as_str())
    }

    pub fn set_query(&mut self, query: String) {
        if self.is_pending() {
            return;
        }
        self.selection.set_query(query);
        self.confirming_delete = None;
    }

    pub fn move_selection(&mut self, delta: i32, sessions: &[SessionItem]) {
        if self.is_pending() {
            return;
        }
        self.selection
            .move_selection(delta, self.filtered_indices(sessions).len());
    }

    pub fn request_delete(&mut self, sessions: &[SessionItem]) -> bool {
        if self.is_pending() {
            return false;
        }
        let Some(session_id) = self.selected_session_id(sessions) else {
            return false;
        };
        self.confirming_delete = Some(session_id.to_string());
        true
    }

    pub fn cancel_delete(&mut self) -> bool {
        if self.is_pending() || self.confirming_delete.is_none() {
            return false;
        }
        self.confirming_delete = None;
        true
    }

    pub fn begin_loading_selected_session(&mut self) -> bool {
        if self.is_pending() {
            return false;
        }
        self.status = SessionsStatus::LoadingSession;
        self.feedback = Some("Loading selected session...".to_string());
        true
    }

    pub fn begin_delete(&mut self) -> Option<String> {
        if self.is_pending() {
            return None;
        }
        let session_id = self.confirming_delete.take()?;
        self.status = SessionsStatus::Deleting;
        self.feedback = Some("Deleting session...".to_string());
        Some(session_id)
    }

    pub fn deleted_session(&mut self, sessions: &[SessionItem]) {
        self.selection
            .clamp_selection(self.filtered_indices(sessions).len());
        self.status = if sessions.is_empty() {
            SessionsStatus::Empty
        } else {
            SessionsStatus::Ready
        };
        self.feedback = Some("Session deleted.".to_string());
    }

    pub fn failed(&mut self, message: impl Into<String>, sessions: &[SessionItem]) {
        self.status = if sessions.is_empty() {
            SessionsStatus::Empty
        } else {
            SessionsStatus::Ready
        };
        self.feedback = Some(message.into());
    }

    pub fn fail_pending(&mut self, message: impl Into<String>, sessions: &[SessionItem]) -> bool {
        if !self.is_pending() {
            return false;
        }
        self.failed(message, sessions);
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sessions() -> Vec<SessionItem> {
        vec![
            SessionItem {
                id: "abc-123".to_string(),
                title: "First session".to_string(),
                count: 1,
                updated_at: "today".to_string(),
            },
            SessionItem {
                id: "def-456".to_string(),
                title: "Release review".to_string(),
                count: 2,
                updated_at: "yesterday".to_string(),
            },
        ]
    }

    #[test]
    fn empty_filter_keeps_navigation_safe() {
        let sessions = sessions();
        let mut picker = SessionsSelectorState::default();
        picker.set_sessions(&sessions);
        picker.set_query("missing".to_string());
        picker.move_selection(1, &sessions);

        assert!(picker.filtered_indices(&sessions).is_empty());
        assert_eq!(picker.selection.selected, 0);
        assert_eq!(picker.selected_session_id(&sessions), None);
    }

    #[test]
    fn session_filter_matches_title_and_id() {
        let sessions = sessions();
        let mut picker = SessionsSelectorState::default();
        picker.set_sessions(&sessions);

        picker.set_query("review".to_string());
        assert_eq!(picker.selected_session_id(&sessions), Some("def-456"));

        picker.set_query("ABC".to_string());
        assert_eq!(picker.selected_session_id(&sessions), Some("abc-123"));
    }

    #[test]
    fn delete_confirmation_can_be_cancelled_without_losing_selection() {
        let sessions = sessions();
        let mut picker = SessionsSelectorState::default();
        picker.set_sessions(&sessions);
        picker.move_selection(1, &sessions);

        assert!(picker.request_delete(&sessions));
        assert_eq!(picker.confirming_delete.as_deref(), Some("def-456"));
        picker.cancel_delete();

        assert_eq!(picker.confirming_delete, None);
        assert_eq!(picker.selected_session_id(&sessions), Some("def-456"));
    }

    #[test]
    fn pending_operations_lock_session_selector_interactions() {
        let sessions = sessions();

        for status in [
            SessionsStatus::Loading,
            SessionsStatus::LoadingSession,
            SessionsStatus::Deleting,
        ] {
            let mut picker = SessionsSelectorState::default();
            picker.set_sessions(&sessions);
            picker.selection.selected = 1;
            picker.selection.query = "review".to_string();
            picker.confirming_delete = Some("def-456".to_string());
            picker.status = status;
            let before = picker.clone();

            assert!(!picker.begin_loading());
            picker.set_query("first".to_string());
            picker.move_selection(1, &sessions);
            assert!(!picker.request_delete(&sessions));
            assert!(!picker.cancel_delete());
            assert!(!picker.begin_loading_selected_session());
            assert_eq!(picker.begin_delete(), None);
            assert_eq!(picker, before, "{status:?} must lock the selector");
        }
    }

    #[test]
    fn pending_operations_fail_to_terminal_feedback_on_disconnect() {
        let sessions = sessions();

        for status in [
            SessionsStatus::Loading,
            SessionsStatus::LoadingSession,
            SessionsStatus::Deleting,
        ] {
            let mut picker = SessionsSelectorState::default();
            picker.set_sessions(&sessions);
            picker.status = status;

            assert!(picker.fail_pending("Backend disconnected.", &sessions));
            assert_eq!(picker.status, SessionsStatus::Ready);
            assert_eq!(picker.feedback.as_deref(), Some("Backend disconnected."));
        }
    }

    #[test]
    fn confirmed_delete_and_acceptance_have_explicit_states() {
        let sessions = sessions();
        let mut picker = SessionsSelectorState::default();
        picker.set_sessions(&sessions);

        assert_eq!(picker.selected_session_id(&sessions), Some("abc-123"));
        assert!(picker.begin_loading_selected_session());
        assert_eq!(picker.status, SessionsStatus::LoadingSession);
        assert!(picker.fail_pending("Backend disconnected.", &sessions));

        assert!(picker.request_delete(&sessions));
        assert_eq!(picker.begin_delete().as_deref(), Some("abc-123"));
        assert_eq!(picker.status, SessionsStatus::Deleting);
    }
}
