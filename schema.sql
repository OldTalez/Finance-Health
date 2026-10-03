-- PostgreSQL Schema for Finance Platform Phase 1
-- Users, accounts, transactions, statements, categorization, and audit trail

-- ===================== USERS =====================
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

CREATE INDEX idx_users_email ON users(email);


-- ===================== ACCOUNTS =====================
-- Debit, credit, savings accounts across different banks
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,  -- e.g. "PC Financial Mastercard", "TD Chequing"
    bank_key VARCHAR(50) NOT NULL,  -- e.g. "PCFinancial-Mastercard", "TD-CashBack"
    account_type VARCHAR(20) NOT NULL,  -- 'credit' | 'debit' | 'savings'
    currency VARCHAR(3) DEFAULT 'CAD',
    import_format VARCHAR(30),  -- 'twoDateAmount' | 'twoDateBalance' | 'twoDateSplitCols' | 'singleDateBalance' | 'endAnchoredSplitCols' | 'CSV'
    latest_balance DECIMAL(12, 2),
    latest_statement_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_accounts_user_id ON accounts(user_id);
CREATE INDEX idx_accounts_bank_key ON accounts(bank_key);


-- ===================== STATEMENTS =====================
-- Metadata for each imported statement (for deduplication and tracking)
CREATE TABLE statements (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    bank_key VARCHAR(50) NOT NULL,
    account_type VARCHAR(20) NOT NULL,
    file_name VARCHAR(255),
    period_start DATE,
    period_end DATE,
    previous_balance DECIMAL(12, 2),
    closing_balance DECIMAL(12, 2),
    minimum_payment DECIMAL(12, 2),
    payment_due_date DATE,
    credit_limit DECIMAL(12, 2),
    available_credit DECIMAL(12, 2),
    statement_hash VARCHAR(64),  -- SHA-256 hash for deduplication
    reconciled BOOLEAN DEFAULT false,
    transaction_count INTEGER DEFAULT 0,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_statements_user_id ON statements(user_id);
CREATE INDEX idx_statements_account_id ON statements(account_id);
CREATE INDEX idx_statements_period ON statements(period_start, period_end);
CREATE INDEX idx_statements_hash ON statements(statement_hash);  -- For deduplication


-- ===================== CATEGORIES =====================
-- Pre-defined expense categories (extensible)
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    is_internal BOOLEAN DEFAULT false,  -- true for transfers, credit card payments, debt payments
    color VARCHAR(7),  -- hex color code for UI
    icon VARCHAR(50),  -- optional icon name
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_categories_user_id ON categories(user_id);
CREATE INDEX idx_categories_is_internal ON categories(is_internal);


-- ===================== RULES =====================
-- Categorization rules: pattern matching for automatic categorization
CREATE TABLE rules (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    pattern VARCHAR(500) NOT NULL,  -- regex pattern to match description
    pattern_type VARCHAR(20) DEFAULT 'regex',  -- 'regex' | 'exact' | 'contains'
    priority INTEGER DEFAULT 0,  -- higher priority = checked first
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_rules_user_id ON rules(user_id);
CREATE INDEX idx_rules_category_id ON rules(category_id);
CREATE INDEX idx_rules_priority ON rules(priority DESC);


-- ===================== TRANSACTIONS =====================
-- Individual transactions imported from statements
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    statement_id INTEGER REFERENCES statements(id) ON DELETE SET NULL,
    category_id INTEGER REFERENCES categories(id),
    date DATE NOT NULL,
    description VARCHAR(500) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,  -- negative = expense, positive = income
    source VARCHAR(50) DEFAULT 'PDF',  -- 'PDF' | 'CSV' | 'manual'
    is_recurring BOOLEAN DEFAULT false,
    recurring_cadence VARCHAR(50),  -- 'Monthly' | 'Weekly' | 'Quarterly' | etc
    flag VARCHAR(50),  -- 'outlier' | 'new_merchant' | etc
    import_id VARCHAR(255),  -- unique ID from original statement for deduplication
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_transactions_user_id ON transactions(user_id);
CREATE INDEX idx_transactions_account_id ON transactions(account_id);
CREATE INDEX idx_transactions_category_id ON transactions(category_id);
CREATE INDEX idx_transactions_date ON transactions(date);
CREATE INDEX idx_transactions_import_id ON transactions(import_id);  -- For deduplication
CREATE INDEX idx_transactions_recurring ON transactions(is_recurring);


-- ===================== RECURRING_CHARGES =====================
-- Summary of detected recurring transactions
CREATE TABLE recurring_charges (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    merchant VARCHAR(255),  -- for non-bill recurring items
    amount DECIMAL(12, 2),  -- typical/median amount
    cadence VARCHAR(50),  -- 'Monthly' | 'Weekly' | 'Quarterly' | 'Annual'
    occurrences INTEGER DEFAULT 1,  -- how many times detected
    last_occurrence DATE,
    next_expected_date DATE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_recurring_user_id ON recurring_charges(user_id);


-- ===================== IMPORT_LOGS =====================
-- Track each import for debugging and audit
CREATE TABLE import_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_name VARCHAR(255),
    file_size INTEGER,
    bank_key VARCHAR(50),
    rows_processed INTEGER,
    rows_imported INTEGER,
    rows_deduplicated INTEGER,
    error_message TEXT,
    import_status VARCHAR(50),  -- 'success' | 'partial' | 'failed'
    ocr_text_sample TEXT,  -- for debugging OCR issues
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_import_logs_user_id ON import_logs(user_id);
CREATE INDEX idx_import_logs_imported_at ON import_logs(imported_at);


-- ===================== AUDIT_LOG =====================
-- User actions for compliance and debugging
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action VARCHAR(100),  -- 'login' | 'import' | 'categorize' | 'delete' | etc
    resource_type VARCHAR(50),  -- 'transaction' | 'statement' | 'rule' | etc
    resource_id INTEGER,
    details JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);
CREATE INDEX idx_audit_log_action ON audit_log(action);
