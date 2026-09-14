-- ============================================================
-- Analytics Platform - MySQL Database Schema
-- 데이터베이스 스키마 (MySQL용)
-- ============================================================

-- 데이터베이스 생성
CREATE DATABASE IF NOT EXISTS analytics_db 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE analytics_db;

-- ============================================================
-- 1. Users Table (사용자 테이블)
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 2. Datasets Table (데이터셋 테이블)
-- ============================================================
CREATE TABLE IF NOT EXISTS datasets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    user_id INT NOT NULL,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    row_count INT,
    column_count INT,
    columns JSON,
    INDEX idx_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 3. Data Records Table (데이터 레코드 테이블)
-- ============================================================
CREATE TABLE IF NOT EXISTS data_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dataset_id INT NOT NULL,
    data JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_dataset_id (dataset_id),
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 4. Data Views Table (데이터 뷰 테이블)
-- ============================================================
CREATE TABLE IF NOT EXISTS data_views (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    dataset_id INT NOT NULL,
    user_id INT NOT NULL,
    view_config JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_dataset_id (dataset_id),
    INDEX idx_user_id (user_id),
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 샘플 데이터 삽입 (Sample Data)
-- ============================================================

-- 샘플 사용자는 기본 비밀번호가 노출되므로 스키마에서 생성하지 않습니다.
-- 필요하면 init_db.py 로 직접 생성하세요 (개발 환경 전용).
-- Sample users are intentionally not created here: seeding a known password
-- hash would ship default credentials. Use init_db.py in development instead.

-- 테이블 확인
SHOW TABLES;

-- 각 테이블 구조 확인
DESCRIBE users;
DESCRIBE datasets;
DESCRIBE data_records;
DESCRIBE data_views;

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
-- 데이터베이스 삭제 (주의!)
-- Drop Database (Warning!)
-- ============================================================
-- DROP DATABASE IF EXISTS analytics_db;
