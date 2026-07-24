//! Session item definition for the `/sessions` interactive overlay.

#[derive(Debug, Clone)]
pub struct SessionItem {
    pub id: String,
    pub title: String,
    pub count: usize,
    pub updated_at: String,
}
