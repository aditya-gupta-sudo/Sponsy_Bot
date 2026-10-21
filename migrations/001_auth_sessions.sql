-- Run with USE sponsybot; This augments only authentication-related storage.
-- Existing event, company, research, contact, and outreach tables are untouched.
ALTER TABLE users ADD COLUMN google_sub VARCHAR(255) NULL;
ALTER TABLE users ADD UNIQUE KEY uq_users_google_sub (google_sub);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at DATETIME NULL,
    INDEX idx_auth_sessions_user (user_id),
    INDEX idx_auth_sessions_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
