-- ============================================================
-- Analytics Platform - SQLite Database Schema
-- 데이터베이스 스키마 (SQLite용)
-- ============================================================

-- SQLite는 자동으로 파일이 생성됩니다: analytics.db
-- SQLite automatically creates the file: analytics.db

-- ============================================================
-- 1. Users Table (사용자 테이블)
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ============================================================
-- 2. Datasets Table (데이터셋 테이블)
-- ============================================================
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    user_id INTEGER NOT NULL,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    row_count INTEGER,
    column_count INTEGER,
    columns TEXT,  -- JSON stored as TEXT in SQLite
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_datasets_user_id ON datasets(user_id);

-- ============================================================
-- 3. Data Records Table (데이터 레코드 테이블)
-- ============================================================
CREATE TABLE IF NOT EXISTS data_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL,
    data TEXT NOT NULL,  -- JSON stored as TEXT in SQLite
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_data_records_dataset_id ON data_records(dataset_id);

-- ============================================================
-- 4. Data Views Table (데이터 뷰 테이블)
-- ============================================================
CREATE TABLE IF NOT EXISTS data_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    dataset_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    view_config TEXT,  -- JSON stored as TEXT in SQLite
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_data_views_dataset_id ON data_views(dataset_id);
CREATE INDEX IF NOT EXISTS idx_data_views_user_id ON data_views(user_id);

-- ============================================================
-- 테이블 목록 확인
-- Check table list
-- ============================================================
-- .tables

-- 테이블 구조 확인
-- Check table structure
-- .schema users
-- .schema datasets
-- .schema data_records
-- .schema data_views

-- ============================================================
-- 유용한 쿼리 (Useful Queries)
-- ============================================================

-- 1. 모든 사용자 조회
-- SELECT * FROM users;

-- 2. 사용자별 데이터셋 수 조회
-- SELECT u.name, u.email, COUNT(d.id) as dataset_count
-- FROM users u
-- LEFT JOIN datasets d ON u.id = d.user_id
-- GROUP BY u.id;

-- 3. 데이터셋별 레코드 수 조회
-- SELECT d.name, d.row_count, COUNT(dr.id) as actual_records
-- FROM datasets d
-- LEFT JOIN data_records dr ON d.id = dr.dataset_id
-- GROUP BY d.id;

-- 4. 최근 업로드된 데이터셋 조회 (상위 10개)
-- SELECT d.name, d.filename, u.name as user_name, d.uploaded_at
-- FROM datasets d
-- JOIN users u ON d.user_id = u.id
-- ORDER BY d.uploaded_at DESC
-- LIMIT 10;

-- ============================================================
-- 데이터베이스 정리 (주의!)
-- Clean Database (Warning!)
-- ============================================================
-- DROP TABLE IF EXISTS data_views;
-- DROP TABLE IF EXISTS data_records;
-- DROP TABLE IF EXISTS datasets;
-- DROP TABLE IF EXISTS users;
