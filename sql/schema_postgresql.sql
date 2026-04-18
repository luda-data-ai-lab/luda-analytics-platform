-- ============================================================
-- Analytics Platform - PostgreSQL Database Schema
-- ============================================================

-- 데이터베이스 생성 (psql 클라이언트에서 직접 실행)
-- CREATE DATABASE analytics_db;
-- \c analytics_db

-- ============================================================
-- 1. Users Table
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    company VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ============================================================
-- 2. Datasets Table
-- ============================================================
CREATE TABLE IF NOT EXISTS datasets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    row_count INTEGER,
    column_count INTEGER,
    columns JSONB,
    is_template BOOLEAN DEFAULT FALSE,
    is_ocr BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_datasets_user_id ON datasets(user_id);

-- ============================================================
-- 3. Data Records Table
-- ============================================================
CREATE TABLE IF NOT EXISTS data_records (
    id SERIAL PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_data_records_dataset_id ON data_records(dataset_id);

-- ============================================================
-- 4. Data Views Table
-- ============================================================
CREATE TABLE IF NOT EXISTS data_views (
    id SERIAL PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    chart_type VARCHAR(50) NOT NULL,
    x_column VARCHAR(100),
    y_column VARCHAR(100),
    config JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_data_views_dataset_id ON data_views(dataset_id);

-- ============================================================
-- 5. OCR Sessions Table
-- ============================================================
CREATE TABLE IF NOT EXISTS ocr_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    extracted_data JSONB,
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 샘플 데이터 (테스트용)
-- ============================================================
-- INSERT INTO users (email, password_hash, name, company) VALUES
-- ('test@example.com', '<hashed_password>', '테스트 사용자', 'LUDA');
