# Gold Scheme Report Generator

An automated report generation system for gold scheme referrals, transactions, and employee data.

## Features

- 📊 Consolidated Report Generation
- 🏢 Branch-wise Scheme Analysis
- 👥 Employee Performance Tracking
- 💰 Payment Matching & Validation
- 📈 Interactive Data Visualization
- 💾 Multi-format Export (Excel/CSV)

## How to Use

1. Upload three files:
   - Employees Report (Excel/CSV)
   - Referrals Report (Excel/CSV)
   - Transactions Report (Excel/CSV)

2. View interactive reports across 5 tabs:
   - Consolidated Report
   - Branch-wise Scheme Report
   - Branch & Employee Scheme Report
   - Branch Summary
   - Employee Performance

3. Export reports in Excel or CSV format

## Required Columns

### Employees Report
- Referral Code
- Employee Code
- Branch
- Employee Type

### Referrals Report
- Referee Name
- Referee Phone
- Referrer Name
- Referrer Phone
- Referral Code
- Status
- Enrollment Amount
- Joined Date OR Registered Date

### Transactions Report
- Customer Phone Number
- Paid Date
- Saved Amount
- Installment number
- Scheme Name
- Passbook number

## Live Demo

[Add your Streamlit Cloud URL here once deployed]

## Local Development

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/gold-scheme-report-generator.git

# Navigate to project directory
cd gold-scheme-report-generator

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py