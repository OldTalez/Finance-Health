# Financial Definitions — T-009 Phase 1 (From Finance Tracker)

**Extracted from:** Dashboard.gs and Analysis.gs (Finance Tracker)  
**Purpose:** Define exact behavior for Dashboard API and recurring detection  
**Status:** Verified against live Finance Tracker code  

---

## 1. Net Worth Calculation

### Definition
```
Net Worth = Sum(debit & savings account balances) − Sum(credit card balances)
```

### Details
- **Balance Source:** Latest statement **closing balance** per account
- **Date Used:** Account's **PeriodEnd** (statement billing period end date)
- **Selection Logic:** For each account, use the statement with the LATEST `PeriodEnd` date, regardless of import order
- **Credit Accounts:** Treated as debt (negative balance)
- **Debit Accounts:** Treated as assets (positive balance)

### Example

```
Statements (by PeriodEnd):
  PC Mastercard    | closing: -$500   | period_end: 2026-09-30 (most recent)
  TD Chequing      | closing: $3,000  | period_end: 2026-09-28
  Savings          | closing: $8,500  | period_end: 2026-09-30 (most recent)
  Wealthsimple     | closing: $1,200  | period_end: 2026-09-25

Net Worth = ($3,000 + $8,500 + $1,200) − ($500)
          = $12,700 − $500
          = $12,200
```

### Why This Matters
- Prevents incorrect net worth if statements are imported out of chronological order
- Uses billing period end date, not import timestamp
- Each account's balance reflects its own statement cycle (not all monthly)

---

## 2. Money-Left-This-Month Definition

### Definition
```
Money Left This Month = Total Income − Total Spending (excluding internal transfers)
  for the most recent month with transaction data
```

### Details
- **"Current Month":** NOT the calendar month (Jan 1–31); rather, the most recent **calendar month** that contains ANY transaction data
  - If latest transaction is Sept 30, "this month" = September (2026-09)
  - If latest transaction is Sept 5, "this month" = September (2026-09)
  - If latest transaction is Oct 1, "this month" = October (2026-10)
- **Period:** All transactions within the calendar month (YYYY-MM-01 to YYYY-MM-31)
- **Income:** All transactions with `amount > 0` AND `category NOT in EXCLUDED_FROM_SPENDING`
- **Spending:** All transactions with `amount < 0` AND `category NOT in EXCLUDED_FROM_SPENDING`
- **Excluded Categories:** Transfer (internal), Credit Card Payment (internal), Debt Payment (internal), KOHO Cover Funds (internal), any category containing "(internal)"

### Example

```
Most recent transaction date: 2026-09-30
Current month key: 2026-09

Transactions in September 2026:
  2026-09-01: Payroll (Income): +$4,500
  2026-09-15: Netflix (Subscriptions): -$24.99
  2026-09-20: CC Payment to Mastercard (Credit Card Payment (internal)): -$500  ← EXCLUDED
  2026-09-28: Transfer to Savings (Transfer (internal)): -$1,000  ← EXCLUDED

Calculation:
  Income = $4,500 (payroll; CC payment & transfer excluded)
  Spending = $24.99 (Netflix)
  Money Left = $4,500 − $24.99 = $4,475.01
```

---

## 3. Recurring Detection Thresholds

### Bill Categories (Fixed Rules)

Categories that are inherently recurring obligations:
- **List:** Rent, Debt Payment, Utilities, Phone Bill, Insurance, Subscriptions

**Detection Rule:** Recurring if appears in 2+ DISTINCT CALENDAR MONTHS
- Example: Rent on Sept 1 and Oct 1 = recurring (2 months)
- Example: Rent on Sept 1 and Sept 15 = NOT recurring (same month, only 1)
- **Amount Tolerance:** NONE (amount can vary)
- **Cadence:** Always labeled "Monthly"
- **Note:** Does NOT require consistent amounts or exact 30-day intervals

### Non-Bill Categories / Merchant Patterns

**Detection Rule:** Recurring if ALL of the following are true:
1. **Minimum Occurrences:** ≥ 3 transactions from the same merchant (normalized description)
2. **Amount Consistency:** All amounts within ±10% of median
   - Example: Median $25, then [$22.50, $27.50] are OK, [$20, $30] are NOT
3. **Cadence Detectable:** Dates match one of:
   - **Daily:** gaps within ±1 day (gap = 1±1 = [0, 2] days)
   - **Weekly:** gaps within ±3 days of 7-day pattern (gap = 7±3 = [4, 10] days)
   - **Monthly:** gaps within ±5 days of 30-day pattern (gap = 30±5 = [25, 35] days)

### Merchant Normalization

Descriptions are normalized before grouping (strip store numbers, dates, special chars):
- `"STARBUCKS #1234 5TH AVE"` → `"starbucks 5th ave"`
- Multiple spaces/punctuation collapsed to single spaces

### Examples

#### Example 1: Bill Category (Rent)
```
Rent transactions (category: "Rent"):
  2026-08-01: -$1,200 (Rent payment)
  2026-09-01: -$1,200 (Rent payment)

Distinct months: 2 (August, September)
→ Recurring: YES, Cadence: Monthly
```

#### Example 2: Subscription (Non-Bill)
```
Netflix transactions (category: "Subscriptions", merchant: "netflix"):
  2026-07-30: -$24.99
  2026-08-30: -$24.99
  2026-09-30: -$24.99

Count: 3 ✓
Amounts: All exactly $24.99 ✓ (0% variance from median $24.99)
Gaps: [31, 31] days ✓ (within [25,35] for monthly)
→ Recurring: YES, Cadence: Monthly
```

#### Example 3: Coffee Shop (Merchant Pattern)
```
Starbucks transactions (normalized: "starbucks"):
  2026-09-01: -$6.50
  2026-09-08: -$5.99
  2026-09-15: -$6.75
  2026-09-22: -$7.00

Count: 4 ✓
Median: $6.50; Range: [$5.99, $7.00] ✓ (within ±10%: [$5.85, $7.15])
Gaps: [7, 7, 7] days ✓ (within [4,10] for weekly)
→ Recurring: YES, Cadence: Weekly
```

#### Example 4: One-Time Purchase (Non-Recurring)
```
Amazon transactions (normalized: "amazon"):
  2026-07-15: -$89.99 (laptop stand)
  2026-09-05: -$45.50 (book)

Count: 2 ✗ (need ≥3)
→ Recurring: NO
```

#### Example 5: Restaurant (Occasional, Not Recurring)
```
Restaurant transactions (normalized: "jose restaurant"):
  2026-08-10: -$45.00
  2026-08-20: -$52.00
  2026-09-05: -$48.00

Count: 3 ✓
Median: $48; Range: [$45, $52] ✓ (within ±10%: [$43.20, $52.80])
Gaps: [10, 16] days ✗ (don't match any cadence pattern)
→ Recurring: NO (cadence doesn't match Daily/Weekly/Monthly)
```

---

## 4. Test Vectors (Sample Transactions)

Real-world examples with expected outputs based on Finance Tracker rules and thresholds.

### CSV Format

```
date,description,amount,category_expected,is_recurring_expected,cadence_expected,flag_expected
```

### Test Vector Data

| # | Date | Description | Amount | Account | Expected Category | Recurring? | Cadence | Flag |
|---|------|-------------|--------|---------|-------------------|-----------|---------|------|
| 1 | 2026-09-30 | NETFLIX MONTHLY CHARGE | -$24.99 | PC Mastercard | Subscriptions | ✓ Yes | Monthly | — |
| 2 | 2026-09-01 | DEPOSIT - PAYROLL | +$4,500.00 | TD Chequing | Income | ✗ No | — | — |
| 3 | 2026-09-15 | UBER EATS - FOOD DELIVERY | -$42.50 | PC Mastercard | Food Delivery | ✗ No | — | — |
| 4 | 2026-09-20 | RENT PAYMENT | -$1,200.00 | TD Chequing | Rent | ✓ Yes | Monthly | — |
| 5 | 2026-09-25 | STARBUCKS #1234 5TH AVE | -$6.50 | PC Mastercard | Coffee | ✓ Yes* | Weekly | — |
| 6 | 2026-09-15 | AMAZON PURCHASE | -$850.00 | PC Mastercard | Shopping | ✗ No | — | ⚠ Outlier |
| 7 | 2026-09-10 | FREEDOM MOBILE PAYMENT | -$75.00 | PC Mastercard | Phone Bill | ✓ Yes | Monthly | — |
| 8 | 2026-09-22 | TRANSFER - TO SAVINGS | -$500.00 | TD Chequing | Transfer (internal) | ✗ No | — | Excl.** |
| 9 | 2026-09-05 | SPOTIFY MUSIC | -$15.99 | PC Mastercard | Subscriptions | ✓ Yes | Monthly | — |
| 10 | 2026-09-18 | WALMART GROCERIES | -$87.50 | PC Mastercard | Groceries | ✗ No | — | — |

### Notes

- **Vector #1 (Netflix):** Subscription; bill category; 2+ months → Recurring Monthly
- **Vector #2 (Payroll):** Income; matches "payroll" rule → Income category
- **Vector #3 (Uber Eats):** Food delivery; matches "uber eats" rule → Food Delivery
- **Vector #4 (Rent):** Bill category in 2+ months → Recurring Monthly
- **Vector #5 (Starbucks):** Merchant pattern; 4+ occurrences weekly (\~$6.50 median) → Recurring Weekly
- **Vector #6 (Amazon $850):** 3.2x median for Shopping category → Outlier flag
- **Vector #7 (Freedom Mobile):** Bill category (Phone Bill) in 2+ months → Recurring Monthly
- **Vector #8 (Transfer):** Internal transfer; excluded from spending/recurring
- **Vector #9 (Spotify):** Subscription category in 2+ months → Recurring Monthly
- **Vector #10 (Walmart):** Groceries; no cadence pattern → Not recurring

**\* Assumes 4+ Starbucks transactions in Sept at \~$6.50, weekly intervals**  
**\*\* Excluded from spending totals, not counted in dashboard "money left"**

---

## Implementation Checklist for Django

- [ ] `RecurringCharge` model with `merchant`, `cadence`, `last_occurrence`, `next_expected_date`
- [ ] Dashboard endpoint returns `net_worth`, `money_left_this_month`, `category_breakdown`
- [ ] Recurring detection task (run after each import) with bill-category and merchant logic
- [ ] Amount tolerance check (±10% of median) for merchant recurrence
- [ ] Cadence detection (daily/weekly/monthly based on gaps)
- [ ] Internal transfer exclusion in `EXCLUDED_FROM_SPENDING`
- [ ] Test vectors validated against real data

---

**Source:** Finance Tracker Dashboard.gs (lines 71–141), Analysis.gs (lines 1–148)  
**Last Updated:** 2026-10-03  
**Ledger Review Status:** Pending
