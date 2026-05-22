import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io
import re

class ReportGenerator:
    def __init__(self, employees_df, referrals_df, transactions_df):
        self.employees_df = employees_df
        self.referrals_df = referrals_df
        self.transactions_df = transactions_df
        
    def clean_phone_number(self, phone):
        """Clean phone number for matching"""
        if pd.isna(phone):
            return ""
        # Convert to string and remove non-numeric characters
        phone_str = str(phone).strip()
        # Keep only digits
        phone_digits = re.sub(r'\D', '', phone_str)
        # Remove leading '91' or '0' if present (optional)
        if phone_digits.startswith('91') and len(phone_digits) == 12:
            phone_digits = phone_digits[2:]
        elif phone_digits.startswith('0') and len(phone_digits) == 11:
            phone_digits = phone_digits[1:]
        return phone_digits
    
    def parse_date_flexible(self, date_val):
        """Parse dates in multiple formats"""
        if pd.isna(date_val):
            return np.nan
        
        try:
            # If it's already a datetime object
            if isinstance(date_val, (datetime, pd.Timestamp)):
                return date_val.date()
            
            date_str = str(date_val).strip()
            
            # Try different date formats
            formats = [
                '%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d', 
                '%m-%d-%Y', '%m/%d/%Y', '%d-%m-%y', 
                '%d/%m/%y', '%b %d, %Y', '%d %b %Y'
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except:
                    continue
            
            # Try pandas to_datetime as last resort
            return pd.to_datetime(date_str).date()
        except:
            return np.nan
    
    def get_updated_date(self, row):
        """Get Updated Date based on Status"""
        status = str(row['Status']).lower().strip() if pd.notna(row['Status']) else ""
        
        # If status contains 'joined' or 'scheme joined', use Joined Date
        if 'joined' in status or 'scheme joined' in status:
            return self.parse_date_flexible(row.get('Joined Date', np.nan))
        # If status contains 'registered' or 'customer register', use Registered Date
        elif 'registered' in status or 'customer register' in status:
            return self.parse_date_flexible(row.get('Registered Date', np.nan))
        # Default to Joined Date if available, otherwise Registered Date
        else:
            if pd.notna(row.get('Joined Date', np.nan)):
                return self.parse_date_flexible(row['Joined Date'])
            else:
                return self.parse_date_flexible(row.get('Registered Date', np.nan))
    
    def transform_branch(self, branch):
        """
        Transform branch name according to the Excel logic with proper case
        """
        if pd.isna(branch) or branch == "":
            return "Bhima Jewellery - Customer"
        
        branch_upper = str(branch).upper().strip()
        
        # Check for special cases (case insensitive)
        if branch_upper == "HEAD OFFICE":
            return "Bhima Jewellery - Madurai"
        elif branch_upper == "IN-TRANSIT- LOCATIONS":
            return "Bhima Jewellery - Salem"
        elif branch_upper == "APP SHOWROOM LOCATION":
            return "Bhima Jewellery - Tirunelveli"
        
        # Check if already has "Bhima Jewellery -"
        if "BHIMA JEWELLERY -" in branch_upper:
            # Extract the part after the prefix and convert to proper case
            parts = str(branch).split("Bhima Jewellery -", 1)
            if len(parts) > 1:
                suffix = parts[1].strip()
                # Convert to proper case (title case)
                suffix = suffix.title()
                final_branch = f"Bhima Jewellery - {suffix}"
            else:
                final_branch = str(branch).title()
        # Check if ends with "BRANCH"
        elif str(branch).upper().strip().endswith("BRANCH"):
            # Remove "BRANCH" and clean
            cleaned = re.sub(r'BRANCH$', '', str(branch), flags=re.IGNORECASE).strip()
            # Convert to proper case
            cleaned = cleaned.title()
            final_branch = f"Bhima Jewellery - {cleaned}"
        else:
            # Convert original branch to proper case
            branch_proper = str(branch).title()
            final_branch = f"Bhima Jewellery - {branch_proper}"
        
        # Replace "Tiruchirappalli" with "Trichy" and ensure proper case
        final_branch = final_branch.replace("Tiruchirappalli", "Trichy")
        final_branch = final_branch.replace("TIRUCHIRAPPALLI", "Trichy")
        final_branch = final_branch.replace("tiruchirappalli", "Trichy")
        
        # Ensure the first letter of each word is capitalized
        # This handles cases like "Bhima Jewellery - salem" -> "Bhima Jewellery - Salem"
        if " - " in final_branch:
            prefix, suffix = final_branch.split(" - ", 1)
            suffix = suffix.title()
            final_branch = f"{prefix} - {suffix}"
        else:
            final_branch = final_branch.title()
        
        return final_branch
    
    def generate_report(self):
        """Generate the final consolidated report"""
        
        # Create a copy of referrals report as base
        final_report = pd.DataFrame()
        
        # 1. Updated Date (Conditional based on Status)
        # Check if both date fields exist
        has_joined_date = 'Joined Date' in self.referrals_df.columns
        has_registered_date = 'Registered Date' in self.referrals_df.columns
        
        if has_joined_date or has_registered_date:
            # Apply conditional date logic
            final_report['Updated Date'] = self.referrals_df.apply(self.get_updated_date, axis=1)
            
            # Show info about date selection
            st.info("📅 Date Logic: Using 'Joined Date' for 'Scheme Joined' status and 'Registered Date' for 'Customer Register' status")
        else:
            st.error("❌ Either 'Joined Date' or 'Registered Date' column must exist in Referrals Report")
            return None
        
        # 2. Customer Name (from Referee Name)
        if 'Referee Name' in self.referrals_df.columns:
            final_report['Customer Name'] = self.referrals_df['Referee Name']
        else:
            st.error("❌ 'Referee Name' column not found in Referrals Report")
            return None
        
        # 3. Customer Phone (from Referee Phone)
        if 'Referee Phone' in self.referrals_df.columns:
            final_report['Customer Phone'] = self.referrals_df['Referee Phone'].apply(self.clean_phone_number)
        else:
            st.error("❌ 'Referee Phone' column not found in Referrals Report")
            return None
        
        # 4. Customer Enrollment Amount (from Enrollment Amount)
        if 'Enrollment Amount' in self.referrals_df.columns:
            final_report['Customer Enrollment Amount'] = pd.to_numeric(self.referrals_df['Enrollment Amount'], errors='coerce')
        else:
            st.error("❌ 'Enrollment Amount' column not found in Referrals Report")
            return None
        
        # 5. Status (from Status)
        if 'Status' in self.referrals_df.columns:
            final_report['Status'] = self.referrals_df['Status']
        else:
            st.error("❌ 'Status' column not found in Referrals Report")
            return None
        
        # 6. Employee Name (from Referrer Name)
        if 'Referrer Name' in self.referrals_df.columns:
            final_report['Employee Name'] = self.referrals_df['Referrer Name']
        else:
            st.error("❌ 'Referrer Name' column not found in Referrals Report")
            return None
        
        # 7. Referral Code (from Referral Code)
        if 'Referral Code' in self.referrals_df.columns:
            final_report['Referral Code'] = self.referrals_df['Referral Code'].astype(str)
        else:
            st.error("❌ 'Referral Code' column not found in Referrals Report")
            return None
        
        # 8. Employee Phone (from Referrer Phone)
        if 'Referrer Phone' in self.referrals_df.columns:
            final_report['Employee Phone'] = self.referrals_df['Referrer Phone'].apply(self.clean_phone_number)
        else:
            st.error("❌ 'Referrer Phone' column not found in Referrals Report")
            return None
        
        # 9. Employee Code (Match with Employees report)
        if 'Referral Code' in self.employees_df.columns and 'Employee Code' in self.employees_df.columns:
            emp_code_dict = dict(zip(
                self.employees_df['Referral Code'].astype(str), 
                self.employees_df['Employee Code']
            ))
            final_report['Employee Code'] = final_report['Referral Code'].map(emp_code_dict)
        else:
            st.warning("⚠️ 'Referral Code' or 'Employee Code' missing in Employees Report")
            final_report['Employee Code'] = np.nan
        
        # 10. Branch (Match with Employees report and apply transformation)
        if 'Referral Code' in self.employees_df.columns and 'Branch' in self.employees_df.columns:
            # Create mapping dictionary
            branch_dict = dict(zip(
                self.employees_df['Referral Code'].astype(str), 
                self.employees_df['Branch']
            ))
            # Get raw branch from employees report
            final_report['Raw Branch'] = final_report['Referral Code'].map(branch_dict)
            # Apply transformation logic with proper case
            final_report['Branch'] = final_report['Raw Branch'].apply(self.transform_branch)
            # Drop the temporary column
            final_report.drop('Raw Branch', axis=1, inplace=True)
            
            # Show branch transformation summary
            st.success("✅ Branch transformation logic applied successfully (Proper Case)")
        else:
            st.warning("⚠️ 'Referral Code' or 'Branch' missing in Employees Report")
            final_report['Branch'] = "Bhima Jewellery - Customer"
        
        # 15. Category (from Employee Type in EMPLOYEES report)
        # Set default to "Customer" if blank or not found
        if 'Referral Code' in self.employees_df.columns and 'Employee Type' in self.employees_df.columns:
            emp_type_dict = dict(zip(
                self.employees_df['Referral Code'].astype(str), 
                self.employees_df['Employee Type']
            ))
            final_report['Category'] = final_report['Referral Code'].map(emp_type_dict)
            # Fill NaN values with "Customer"
            final_report['Category'] = final_report['Category'].fillna('Customer')
        else:
            st.warning("⚠️ 'Referral Code' or 'Employee Type' missing in Employees Report")
            # If columns missing, set all to "Customer"
            final_report['Category'] = 'Customer'
        
        # Prepare transactions data for matching
        # Filter only installment number = 1
        if 'Installment number' in self.transactions_df.columns:
            # Convert to numeric for comparison
            self.transactions_df['Installment number'] = pd.to_numeric(self.transactions_df['Installment number'], errors='coerce')
            trans_filtered = self.transactions_df[self.transactions_df['Installment number'] == 1].copy()
            st.info(f"📊 Transactions with Installment number = 1: {len(trans_filtered)} out of {len(self.transactions_df)} total transactions")
        else:
            st.warning("⚠️ 'Installment number' column not found, using all transactions")
            trans_filtered = self.transactions_df.copy()
        
        # Clean phone numbers in transactions
        if 'Customer Phone Number' in trans_filtered.columns:
            trans_filtered['Clean Phone'] = trans_filtered['Customer Phone Number'].apply(self.clean_phone_number)
        else:
            st.error("❌ 'Customer Phone Number' column not found in Transactions Report")
            return None
        
        # Parse dates in transactions
        if 'Paid Date' in trans_filtered.columns:
            trans_filtered['Paid Date Clean'] = trans_filtered['Paid Date'].apply(self.parse_date_flexible)
        else:
            st.error("❌ 'Paid Date' column not found in Transactions Report")
            return None
        
        # Create lookup dictionaries for faster matching
        # Create a composite key of phone + date
        trans_filtered['Match Key'] = trans_filtered['Clean Phone'] + "_" + trans_filtered['Paid Date Clean'].astype(str)
        
        # Create dictionary for quick lookup
        transaction_lookup = {}
        for idx, row in trans_filtered.iterrows():
            key = row['Match Key']
            transaction_lookup[key] = {
                'saved_amount': row['Saved Amount'] if 'Saved Amount' in row else np.nan,
                'scheme_name': row.get('Scheme Name', '') if 'Scheme Name' in row else '',
                'passbook_no': row.get('Passbook number', '') if 'Passbook number' in row else ''
            }
        
        # 11, 13, 14: Match Customer Payment, Scheme Name, Scheme Passbook Number
        def get_transaction_details(row):
            customer_phone = row['Customer Phone']
            updated_date = row['Updated Date']
            
            if pd.isna(updated_date) or customer_phone == "":
                return np.nan, "", ""
            
            # Create match key
            match_key = customer_phone + "_" + str(updated_date)
            
            # Look up in dictionary
            if match_key in transaction_lookup:
                match = transaction_lookup[match_key]
                return match['saved_amount'], match['scheme_name'], match['passbook_no']
            else:
                return np.nan, "", ""
        
        # Apply transaction matching
        transaction_details = final_report.apply(get_transaction_details, axis=1, result_type='expand')
        final_report['Customer Payment'] = transaction_details[0]
        final_report['Scheme Name'] = transaction_details[1]
        final_report['Scheme Passbook Number'] = transaction_details[2]
        
        # 12. True/False (Compare Enrollment Amount with Customer Payment)
        final_report['True/False'] = np.where(
            final_report['Customer Enrollment Amount'] == final_report['Customer Payment'],
            True,
            False
        )
        
        # Add Not Enrolled flag (customers without payment)
        final_report['Not Enrolled'] = final_report['Customer Payment'].isna()
        
        # 16. Month (extract month name from Updated Date)
        final_report['Month'] = final_report['Updated Date'].apply(
            lambda x: x.strftime('%B').lower() if pd.notna(x) else ''
        )
        
        # Select final columns in the specified order
        final_columns = [
            'Updated Date', 'Customer Name', 'Customer Phone', 'Customer Enrollment Amount',
            'Status', 'Employee Name', 'Referral Code', 'Employee Phone', 'Employee Code',
            'Branch', 'Customer Payment', 'True/False', 'Scheme Name', 'Scheme Passbook Number',
            'Category', 'Month', 'Not Enrolled'
        ]
        
        # Ensure all columns exist
        for col in final_columns:
            if col not in final_report.columns:
                final_report[col] = np.nan
        
        # Show match statistics
        matched_count = final_report['Customer Payment'].notna().sum()
        not_enrolled_count = final_report['Not Enrolled'].sum()
        if len(final_report) > 0:
            st.info(f"📊 Match Results: {matched_count} out of {len(final_report)} records matched with transactions ({matched_count/len(final_report)*100:.1f}%)")
            st.info(f"📊 Not Enrolled Customers: {not_enrolled_count} out of {len(final_report)} ({not_enrolled_count/len(final_report)*100:.1f}%)")
        
        # Show category distribution
        category_counts = final_report['Category'].value_counts()
        st.info(f"📊 Category Distribution: {dict(category_counts)}")
        
        # Show branch distribution
        branch_counts = final_report['Branch'].value_counts().head(10)
        st.info(f"📊 Top 10 Branches: {dict(branch_counts)}")
        
        return final_report[final_columns]
    
    def generate_branch_wise_scheme_report(self, final_report):
        """
        Generate Branch-wise Scheme Consolidation Report
        Shows scheme distribution and performance by branch
        """
        # Filter out records without scheme name
        report_data = final_report[final_report['Scheme Name'].notna() & (final_report['Scheme Name'] != '')].copy()
        
        if len(report_data) == 0:
            return pd.DataFrame()
        
        # Create branch-wise scheme consolidation
        branch_scheme_report = report_data.groupby(['Branch', 'Scheme Name']).agg({
            'Customer Name': 'count',
            'Customer Enrollment Amount': 'sum',
            'Customer Payment': 'sum',
            'True/False': 'sum',
            'Employee Name': 'nunique',  # Unique employees who sold this scheme
            'Referral Code': 'nunique'   # Unique referral codes used
        }).reset_index()
        
        branch_scheme_report.columns = [
            'Branch', 'Scheme Name', 'Number of Customers', 
            'Total Enrollment Amount', 'Total Payment Received', 
            'Number of Matched Payments', 'Unique Employees', 'Unique Referral Codes'
        ]
        
        # Calculate match rate and pending amount
        branch_scheme_report['Match Rate (%)'] = (
            branch_scheme_report['Number of Matched Payments'] / 
            branch_scheme_report['Number of Customers'] * 100
        ).round(2)
        
        branch_scheme_report['Pending Amount'] = (
            branch_scheme_report['Total Enrollment Amount'] - 
            branch_scheme_report['Total Payment Received']
        )
        
        # Sort by branch and number of customers
        branch_scheme_report = branch_scheme_report.sort_values(['Branch', 'Number of Customers'], ascending=[True, False])
        
        return branch_scheme_report
    
    def generate_branch_employee_wise_scheme_report(self, final_report):
        """
        Generate Branch and Employee-wise Scheme Report
        Shows scheme performance by branch and individual employees
        """
        # Filter out records without scheme name
        report_data = final_report[final_report['Scheme Name'].notna() & (final_report['Scheme Name'] != '')].copy()
        
        if len(report_data) == 0:
            return pd.DataFrame()
        
        # Create branch-employee-scheme report
        emp_scheme_report = report_data.groupby(['Branch', 'Employee Name', 'Employee Code', 'Referral Code', 'Scheme Name']).agg({
            'Customer Name': 'count',
            'Customer Enrollment Amount': 'sum',
            'Customer Payment': 'sum',
            'True/False': 'sum',
            'Customer Phone': 'nunique'  # Unique customers
        }).reset_index()
        
        emp_scheme_report.columns = [
            'Branch', 'Employee Name', 'Employee Code', 'Referral Code', 'Scheme Name',
            'Number of Customers', 'Total Enrollment Amount', 'Total Payment Received',
            'Number of Matched Payments', 'Unique Customers'
        ]
        
        # Calculate match rate and average per customer
        emp_scheme_report['Match Rate (%)'] = (
            emp_scheme_report['Number of Matched Payments'] / 
            emp_scheme_report['Number of Customers'] * 100
        ).round(2)
        
        emp_scheme_report['Average Enrollment Amount'] = (
            emp_scheme_report['Total Enrollment Amount'] / 
            emp_scheme_report['Number of Customers']
        ).round(2)
        
        emp_scheme_report['Pending Amount'] = (
            emp_scheme_report['Total Enrollment Amount'] - 
            emp_scheme_report['Total Payment Received']
        )
        
        # Sort by branch and number of customers
        emp_scheme_report = emp_scheme_report.sort_values(
            ['Branch', 'Employee Name', 'Number of Customers'], 
            ascending=[True, True, False]
        )
        
        return emp_scheme_report
    
    def generate_branch_summary_report(self, final_report):
        """
        Generate Branch-wise Summary Report (Overall performance by branch)
        """
        branch_summary = final_report.groupby('Branch').agg({
            'Customer Name': 'count',
            'Customer Enrollment Amount': 'sum',
            'Customer Payment': 'sum',
            'True/False': 'sum',
            'Employee Name': 'nunique',
            'Referral Code': 'nunique',  # Count unique referral codes used
            'Scheme Name': lambda x: x.notna().sum(),  # Count schemes sold
            'Not Enrolled': 'sum'  # Count not enrolled customers
        }).reset_index()
        
        branch_summary.columns = [
            'Branch', 'Total Customers', 'Total Enrollment Amount', 
            'Total Payment Received', 'Matched Payments', 'Unique Employees', 
            'Unique Referral Codes', 'Schemes Sold', 'Not Enrolled'
        ]
        
        # Calculate additional metrics
        branch_summary['Match Rate (%)'] = (
            branch_summary['Matched Payments'] / branch_summary['Total Customers'] * 100
        ).round(2)
        
        branch_summary['Enrollment Rate (%)'] = (
            (branch_summary['Total Customers'] - branch_summary['Not Enrolled']) / 
            branch_summary['Total Customers'] * 100
        ).round(2)
        
        branch_summary['Pending Amount'] = (
            branch_summary['Total Enrollment Amount'] - branch_summary['Total Payment Received']
        )
        
        branch_summary['Average Enrollment Amount'] = (
            branch_summary['Total Enrollment Amount'] / branch_summary['Total Customers']
        ).round(2)
        
        # Sort by total customers
        branch_summary = branch_summary.sort_values('Total Customers', ascending=False)
        
        return branch_summary
    
    def generate_employee_performance_report(self, final_report):
        """
        Generate Employee Performance Report (Overall performance by employee)
        """
        emp_performance = final_report.groupby(['Employee Name', 'Employee Code', 'Referral Code', 'Branch', 'Category']).agg({
            'Customer Name': 'count',
            'Customer Enrollment Amount': 'sum',
            'Customer Payment': 'sum',
            'True/False': 'sum',
            'Scheme Name': lambda x: x.notna().sum(),
            'Not Enrolled': 'sum'
        }).reset_index()
        
        emp_performance.columns = [
            'Employee Name', 'Employee Code', 'Referral Code', 'Branch', 'Category',
            'Total Customers', 'Total Enrollment Amount', 'Total Payment Received',
            'Matched Payments', 'Schemes Sold', 'Not Enrolled'
        ]
        
        # Calculate metrics
        emp_performance['Match Rate (%)'] = (
            emp_performance['Matched Payments'] / emp_performance['Total Customers'] * 100
        ).round(2)
        
        emp_performance['Enrollment Rate (%)'] = (
            (emp_performance['Total Customers'] - emp_performance['Not Enrolled']) / 
            emp_performance['Total Customers'] * 100
        ).round(2)
        
        emp_performance['Average Enrollment Amount'] = (
            emp_performance['Total Enrollment Amount'] / emp_performance['Total Customers']
        ).round(2)
        
        emp_performance['Pending Amount'] = (
            emp_performance['Total Enrollment Amount'] - emp_performance['Total Payment Received']
        )
        
        # Sort by total customers
        emp_performance = emp_performance.sort_values('Total Customers', ascending=False)
        
        return emp_performance
    
    def generate_registration_analysis_report(self, final_report):
        """
        Generate Registration Analysis Report
        Shows registration counts, enrollment status, and not enrolled customers
        """
        # Create registration analysis report
        reg_analysis = final_report.copy()
        
        # Add registration status based on payment and status
        def get_registration_status(row):
            if pd.notna(row['Customer Payment']):
                return 'Enrolled (Payment Made)'
            elif 'joined' in str(row['Status']).lower() or 'scheme joined' in str(row['Status']).lower():
                return 'Registered but Not Enrolled'
            elif 'registered' in str(row['Status']).lower() or 'customer register' in str(row['Status']).lower():
                return 'Registered but Not Enrolled'
            else:
                return 'Not Enrolled'
        
        reg_analysis['Registration Status'] = reg_analysis.apply(get_registration_status, axis=1)
        
        # Summary by branch and status
        branch_reg_summary = reg_analysis.groupby(['Branch', 'Registration Status']).agg({
            'Customer Name': 'count',
            'Customer Enrollment Amount': 'sum',
            'Customer Payment': 'sum',
            'Referral Code': 'nunique'  # Count unique referral codes
        }).reset_index()
        
        branch_reg_summary.columns = [
            'Branch', 'Registration Status', 'Customer Count', 
            'Total Enrollment Amount', 'Total Payment Received', 'Unique Referral Codes'
        ]
        
        # Pivot table for better visualization
        branch_reg_pivot = branch_reg_summary.pivot_table(
            index='Branch',
            columns='Registration Status',
            values='Customer Count',
            fill_value=0
        ).reset_index()
        
        # Add total registrations
        if 'Enrolled (Payment Made)' in branch_reg_pivot.columns:
            branch_reg_pivot['Total Enrolled'] = branch_reg_pivot['Enrolled (Payment Made)']
        else:
            branch_reg_pivot['Total Enrolled'] = 0
            
        if 'Registered but Not Enrolled' in branch_reg_pivot.columns:
            branch_reg_pivot['Total Registered'] = branch_reg_pivot['Registered but Not Enrolled']
        else:
            branch_reg_pivot['Total Registered'] = 0
            
        if 'Not Enrolled' in branch_reg_pivot.columns:
            branch_reg_pivot['Total Not Enrolled'] = branch_reg_pivot['Not Enrolled']
        else:
            branch_reg_pivot['Total Not Enrolled'] = 0
        
        branch_reg_pivot['Total Customers'] = (
            branch_reg_pivot['Total Enrolled'] + 
            branch_reg_pivot['Total Registered'] + 
            branch_reg_pivot['Total Not Enrolled']
        )
        
        branch_reg_pivot['Enrollment Rate (%)'] = (
            branch_reg_pivot['Total Enrolled'] / branch_reg_pivot['Total Customers'] * 100
        ).round(2)
        
        # Sort by total customers
        branch_reg_pivot = branch_reg_pivot.sort_values('Total Customers', ascending=False)
        
        # Detailed not enrolled customers list (include referral code)
        not_enrolled_customers = final_report[final_report['Not Enrolled'] == True].copy()
        not_enrolled_customers = not_enrolled_customers[[
            'Customer Name', 'Customer Phone', 'Employee Name', 'Employee Code', 
            'Referral Code', 'Branch', 'Status', 'Customer Enrollment Amount', 'Updated Date'
        ]]
        
        return branch_reg_pivot, not_enrolled_customers

def main():
    st.set_page_config(page_title="Report Generator System", layout="wide")
    
    # Custom CSS
    st.markdown("""
    <style>
    .main-header {
        background-color: #1E3A8A;
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .success-box {
        background-color: #D1FAE5;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #10B981;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #FEF3C7;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #F59E0B;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #DBEAFE;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #3B82F6;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #FEE2E2;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #EF4444;
        margin: 1rem 0;
    }
    .report-card {
        background-color: #F3F4F6;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        cursor: pointer;
        transition: transform 0.2s;
    }
    .report-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="main-header"><h1>📊 Automated Report Generator</h1><p>Generate consolidated reports from Employees, Referrals, and Transactions data</p></div>', unsafe_allow_html=True)
    
    # File upload section
    col1, col2, col3 = st.columns(3)
    
    with col1:
        employees_file = st.file_uploader(
            "📁 Employees Report",
            type=['xlsx', 'xls', 'csv'],
            help="Upload Excel or CSV file containing employee data",
            key="emp_file"
        )
        if employees_file:
            st.success("✅ Employees file uploaded")
    
    with col2:
        referrals_file = st.file_uploader(
            "📁 Referrals Report",
            type=['xlsx', 'xls', 'csv'],
            help="Upload Excel or CSV file containing referral data",
            key="ref_file"
        )
        if referrals_file:
            st.success("✅ Referrals file uploaded")
    
    with col3:
        transactions_file = st.file_uploader(
            "📁 Transactions Report",
            type=['xlsx', 'xls', 'csv'],
            help="Upload Excel or CSV file containing transaction data",
            key="trans_file"
        )
        if transactions_file:
            st.success("✅ Transactions file uploaded")
    
    # Process files when all are uploaded
    if employees_file and referrals_file and transactions_file:
        try:
            # Load files
            with st.spinner("Loading files..."):
                # Load Employees Report
                if employees_file.name.endswith('.csv'):
                    employees_df = pd.read_csv(employees_file)
                else:
                    employees_df = pd.read_excel(employees_file)
                
                # Load Referrals Report
                if referrals_file.name.endswith('.csv'):
                    referrals_df = pd.read_csv(referrals_file)
                else:
                    referrals_df = pd.read_excel(referrals_file)
                
                # Load Transactions Report
                if transactions_file.name.endswith('.csv'):
                    transactions_df = pd.read_csv(transactions_file)
                else:
                    transactions_df = pd.read_excel(transactions_file)
            
            # Check for required date columns in referrals
            has_joined_date = 'Joined Date' in referrals_df.columns
            has_registered_date = 'Registered Date' in referrals_df.columns
            
            if not has_joined_date and not has_registered_date:
                st.error("❌ Referrals Report must contain either 'Joined Date' or 'Registered Date' column")
                st.stop()
            
            # Generate report
            with st.spinner("Generating consolidated report..."):
                generator = ReportGenerator(employees_df, referrals_df, transactions_df)
                final_report = generator.generate_report()
                
                if final_report is None:
                    st.error("Failed to generate report. Please check your data.")
                    st.stop()
            
            # Display success message
            st.markdown('<div class="success-box">✅ Report generated successfully!</div>', unsafe_allow_html=True)
            
            # Create tabs for different reports
            tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
                "📋 Consolidated Report", 
                "🏢 Branch-wise Scheme Report", 
                "👥 Branch & Employee Scheme Report",
                "📊 Branch Summary",
                "⭐ Employee Performance",
                "📝 Registration Analysis"
            ])
            
            with tab1:
                st.subheader("📈 Final Consolidated Report")
                st.dataframe(final_report, use_container_width=True, height=400)
                
                # Statistics
                st.subheader("📊 Report Statistics")
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                
                with col1:
                    st.metric("Total Records", len(final_report))
                
                with col2:
                    total_amount = final_report['Customer Enrollment Amount'].sum()
                    st.metric("Total Enrollment Amount", f"₹{total_amount:,.2f}" if pd.notna(total_amount) else "₹0")
                
                with col3:
                    total_payment = final_report['Customer Payment'].sum()
                    st.metric("Total Payments", f"₹{total_payment:,.2f}" if pd.notna(total_payment) else "₹0")
                
                with col4:
                    matched = final_report['True/False'].sum() if 'True/False' in final_report.columns else 0
                    st.metric("Matched Records", int(matched))
                
                with col5:
                    match_percent = (matched / len(final_report) * 100) if len(final_report) > 0 else 0
                    st.metric("Match Rate", f"{match_percent:.1f}%")
                
                with col6:
                    not_enrolled = final_report['Not Enrolled'].sum() if 'Not Enrolled' in final_report.columns else 0
                    st.metric("Not Enrolled", int(not_enrolled))
            
            with tab2:
                st.subheader("🏢 Branch-wise Scheme Consolidation Report")
                st.markdown("Shows scheme distribution and performance metrics by branch")
                
                branch_scheme_report = generator.generate_branch_wise_scheme_report(final_report)
                
                if len(branch_scheme_report) > 0:
                    # Add filters
                    col1, col2 = st.columns(2)
                    with col1:
                        branches = ['All'] + sorted(branch_scheme_report['Branch'].unique().tolist())
                        selected_branch = st.selectbox("Filter by Branch", branches, key="branch_scheme_filter")
                    
                    with col2:
                        schemes = ['All'] + sorted(branch_scheme_report['Scheme Name'].unique().tolist())
                        selected_scheme = st.selectbox("Filter by Scheme", schemes, key="scheme_filter")
                    
                    # Apply filters
                    filtered_report = branch_scheme_report.copy()
                    if selected_branch != 'All':
                        filtered_report = filtered_report[filtered_report['Branch'] == selected_branch]
                    if selected_scheme != 'All':
                        filtered_report = filtered_report[filtered_report['Scheme Name'] == selected_scheme]
                    
                    # Display metrics
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Total Schemes", filtered_report['Scheme Name'].nunique())
                    with col2:
                        st.metric("Total Customers", filtered_report['Number of Customers'].sum())
                    with col3:
                        st.metric("Total Revenue", f"₹{filtered_report['Total Enrollment Amount'].sum():,.2f}")
                    with col4:
                        st.metric("Avg Match Rate", f"{filtered_report['Match Rate (%)'].mean():.1f}%")
                    
                    # Display the report
                    st.dataframe(filtered_report, use_container_width=True)
                    
                    # Visualization
                    st.subheader("📊 Top Schemes by Branch")
                    top_schemes = branch_scheme_report.groupby('Scheme Name')['Number of Customers'].sum().sort_values(ascending=False).head(10)
                    st.bar_chart(top_schemes)
                else:
                    st.info("No scheme data available for branch-wise analysis")
            
            with tab3:
                st.subheader("👥 Branch & Employee-wise Scheme Report")
                st.markdown("Shows scheme performance by branch and individual employees (includes Referral Code)")
                
                emp_scheme_report = generator.generate_branch_employee_wise_scheme_report(final_report)
                
                if len(emp_scheme_report) > 0:
                    # Add filters
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        branches = ['All'] + sorted(emp_scheme_report['Branch'].unique().tolist())
                        selected_branch = st.selectbox("Filter by Branch", branches, key="emp_branch_filter")
                    
                    with col2:
                        if selected_branch != 'All':
                            employees = ['All'] + sorted(emp_scheme_report[emp_scheme_report['Branch'] == selected_branch]['Employee Name'].unique().tolist())
                        else:
                            employees = ['All'] + sorted(emp_scheme_report['Employee Name'].unique().tolist())
                        selected_employee = st.selectbox("Filter by Employee", employees, key="emp_filter")
                    
                    with col3:
                        schemes = ['All'] + sorted(emp_scheme_report['Scheme Name'].unique().tolist())
                        selected_scheme = st.selectbox("Filter by Scheme", schemes, key="emp_scheme_filter")
                    
                    # Apply filters
                    filtered_report = emp_scheme_report.copy()
                    if selected_branch != 'All':
                        filtered_report = filtered_report[filtered_report['Branch'] == selected_branch]
                    if selected_employee != 'All':
                        filtered_report = filtered_report[filtered_report['Employee Name'] == selected_employee]
                    if selected_scheme != 'All':
                        filtered_report = filtered_report[filtered_report['Scheme Name'] == selected_scheme]
                    
                    # Display metrics
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        st.metric("Total Employees", filtered_report['Employee Name'].nunique())
                    with col2:
                        st.metric("Total Schemes", filtered_report['Scheme Name'].nunique())
                    with col3:
                        st.metric("Total Customers", filtered_report['Number of Customers'].sum())
                    with col4:
                        st.metric("Total Revenue", f"₹{filtered_report['Total Enrollment Amount'].sum():,.2f}")
                    with col5:
                        st.metric("Avg Match Rate", f"{filtered_report['Match Rate (%)'].mean():.1f}%")
                    
                    # Display the report with Referral Code
                    display_columns = ['Branch', 'Employee Name', 'Employee Code', 'Referral Code', 'Scheme Name',
                                      'Number of Customers', 'Total Enrollment Amount', 'Total Payment Received',
                                      'Match Rate (%)', 'Average Enrollment Amount']
                    st.dataframe(filtered_report[display_columns], use_container_width=True)
                    
                    # Top performing employees
                    st.subheader("🏆 Top Performing Employees by Customer Count")
                    top_employees = emp_scheme_report.groupby(['Employee Name', 'Referral Code']).agg({
                        'Number of Customers': 'sum',
                        'Total Enrollment Amount': 'sum'
                    }).sort_values('Number of Customers', ascending=False).head(10)
                    st.dataframe(top_employees, use_container_width=True)
                else:
                    st.info("No scheme data available for employee-wise analysis")
            
            with tab4:
                st.subheader("📊 Branch Summary Report")
                st.markdown("Overall performance summary by branch")
                
                branch_summary = generator.generate_branch_summary_report(final_report)
                
                if len(branch_summary) > 0:
                    # Display metrics
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        st.metric("Total Branches", len(branch_summary))
                    with col2:
                        st.metric("Total Customers", branch_summary['Total Customers'].sum())
                    with col3:
                        st.metric("Total Revenue", f"₹{branch_summary['Total Enrollment Amount'].sum():,.2f}")
                    with col4:
                        st.metric("Overall Match Rate", f"{branch_summary['Match Rate (%)'].mean():.1f}%")
                    with col5:
                        st.metric("Not Enrolled", branch_summary['Not Enrolled'].sum())
                    
                    # Display the report
                    st.dataframe(branch_summary, use_container_width=True)
                    
                    # Visualization
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("Top 10 Branches by Customers")
                        top_branches = branch_summary.head(10)
                        st.bar_chart(top_branches.set_index('Branch')['Total Customers'])
                    
                    with col2:
                        st.subheader("Enrollment Rate by Branch")
                        st.bar_chart(top_branches.set_index('Branch')['Enrollment Rate (%)'])
                else:
                    st.info("No branch summary data available")
            
            with tab5:
                st.subheader("⭐ Employee Performance Report")
                st.markdown("Overall performance metrics by employee")
                
                emp_performance = generator.generate_employee_performance_report(final_report)
                
                if len(emp_performance) > 0:
                    # Add filters
                    col1, col2 = st.columns(2)
                    with col1:
                        categories = ['All'] + sorted(emp_performance['Category'].unique().tolist())
                        selected_category = st.selectbox("Filter by Category", categories)
                    
                    with col2:
                        branches = ['All'] + sorted(emp_performance['Branch'].unique().tolist())
                        selected_branch = st.selectbox("Filter by Branch", branches, key="perf_branch_filter")
                    
                    # Apply filters
                    filtered_performance = emp_performance.copy()
                    if selected_category != 'All':
                        filtered_performance = filtered_performance[filtered_performance['Category'] == selected_category]
                    if selected_branch != 'All':
                        filtered_performance = filtered_performance[filtered_performance['Branch'] == selected_branch]
                    
                    # Display metrics
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        st.metric("Total Employees", len(filtered_performance))
                    with col2:
                        st.metric("Total Customers", filtered_performance['Total Customers'].sum())
                    with col3:
                        st.metric("Total Revenue", f"₹{filtered_performance['Total Enrollment Amount'].sum():,.2f}")
                    with col4:
                        st.metric("Average per Employee", f"₹{(filtered_performance['Total Enrollment Amount'].sum() / len(filtered_performance)):,.0f}" if len(filtered_performance) > 0 else "₹0")
                    with col5:
                        st.metric("Avg Enrollment Rate", f"{filtered_performance['Enrollment Rate (%)'].mean():.1f}%")
                    
                    # Display the report with Referral Code column
                    display_columns = ['Employee Name', 'Employee Code', 'Referral Code', 'Branch', 'Category', 
                                      'Total Customers', 'Total Enrollment Amount', 'Total Payment Received',
                                      'Matched Payments', 'Schemes Sold', 'Enrollment Rate (%)', 'Match Rate (%)']
                    st.dataframe(filtered_performance[display_columns], use_container_width=True)
                    
                    # Top employees
                    st.subheader("🏆 Top 10 Employees by Customer Count")
                    top_employees = filtered_performance.head(10)
                    st.dataframe(top_employees[['Employee Name', 'Referral Code', 'Branch', 'Total Customers', 
                                               'Total Enrollment Amount', 'Enrollment Rate (%)', 'Match Rate (%)']], 
                                use_container_width=True)
                else:
                    st.info("No employee performance data available")
            
            with tab6:
                st.subheader("📝 Registration Analysis Report")
                st.markdown("Shows registration counts, enrollment status, and not enrolled customers")
                
                reg_pivot, not_enrolled_customers = generator.generate_registration_analysis_report(final_report)
                
                # Registration Summary Dashboard
                st.subheader("📊 Registration Summary")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Registered Customers", len(final_report))
                with col2:
                    enrolled = len(final_report[final_report['Not Enrolled'] == False])
                    st.metric("Enrolled Customers", enrolled)
                with col3:
                    not_enrolled_count = len(not_enrolled_customers)
                    st.metric("Not Enrolled Customers", not_enrolled_count, delta=f"{(not_enrolled_count/len(final_report)*100):.1f}%")
                with col4:
                    enrollment_rate = (enrolled/len(final_report)*100) if len(final_report) > 0 else 0
                    st.metric("Enrollment Rate", f"{enrollment_rate:.1f}%")
                
                # Branch-wise Registration Summary
                st.subheader("🏢 Branch-wise Registration Status")
                st.dataframe(reg_pivot, use_container_width=True)
                
                # Filter for branch registration view
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Branch Registration Distribution")
                    branch_reg_chart = reg_pivot.set_index('Branch')[['Total Enrolled', 'Total Registered', 'Total Not Enrolled']]
                    st.bar_chart(branch_reg_chart)
                
                with col2:
                    st.subheader("Enrollment Rate by Branch")
                    enrollment_rate_chart = reg_pivot.set_index('Branch')['Enrollment Rate (%)']
                    st.bar_chart(enrollment_rate_chart)
                
                # Not Enrolled Customers List
                st.subheader("❌ Not Enrolled Customers Details")
                if len(not_enrolled_customers) > 0:
                    # Add filters for not enrolled customers
                    col1, col2 = st.columns(2)
                    with col1:
                        branches = ['All'] + sorted(not_enrolled_customers['Branch'].unique().tolist())
                        filter_branch = st.selectbox("Filter by Branch", branches, key="not_enrolled_branch")
                    
                    with col2:
                        statuses = ['All'] + sorted(not_enrolled_customers['Status'].unique().tolist())
                        filter_status = st.selectbox("Filter by Status", statuses, key="not_enrolled_status")
                    
                    # Apply filters
                    filtered_not_enrolled = not_enrolled_customers.copy()
                    if filter_branch != 'All':
                        filtered_not_enrolled = filtered_not_enrolled[filtered_not_enrolled['Branch'] == filter_branch]
                    if filter_status != 'All':
                        filtered_not_enrolled = filtered_not_enrolled[filtered_not_enrolled['Status'] == filter_status]
                    
                    # Display metrics for filtered not enrolled
                    st.markdown(f"**Showing {len(filtered_not_enrolled)} not enrolled customers**")
                    st.dataframe(filtered_not_enrolled, use_container_width=True)
                    
                    # Export not enrolled customers
                    csv_buffer = io.StringIO()
                    filtered_not_enrolled.to_csv(csv_buffer, index=False)
                    st.download_button(
                        label="📥 Download Not Enrolled Customers (CSV)",
                        data=csv_buffer.getvalue(),
                        file_name=f"not_enrolled_customers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                else:
                    st.info("✅ All customers are enrolled! No not enrolled customers found.")
            
            # Export options
            st.subheader("💾 Export All Reports")
            
            col1, col2, col3 = st.columns(3)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            with col1:
                # Export all reports to Excel
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    final_report.to_excel(writer, sheet_name='Consolidated Report', index=False)
                    
                    branch_scheme = generator.generate_branch_wise_scheme_report(final_report)
                    if len(branch_scheme) > 0:
                        branch_scheme.to_excel(writer, sheet_name='Branch-wise Scheme', index=False)
                    
                    emp_scheme = generator.generate_branch_employee_wise_scheme_report(final_report)
                    if len(emp_scheme) > 0:
                        emp_scheme.to_excel(writer, sheet_name='Branch-Employee Scheme', index=False)
                    
                    branch_summary = generator.generate_branch_summary_report(final_report)
                    if len(branch_summary) > 0:
                        branch_summary.to_excel(writer, sheet_name='Branch Summary', index=False)
                    
                    emp_performance = generator.generate_employee_performance_report(final_report)
                    if len(emp_performance) > 0:
                        emp_performance.to_excel(writer, sheet_name='Employee Performance', index=False)
                    
                    # Add registration analysis
                    reg_pivot, not_enrolled = generator.generate_registration_analysis_report(final_report)
                    if len(reg_pivot) > 0:
                        reg_pivot.to_excel(writer, sheet_name='Registration Analysis', index=False)
                    if len(not_enrolled) > 0:
                        not_enrolled.to_excel(writer, sheet_name='Not Enrolled Customers', index=False)
                    
                    # Add unmatched records sheet
                    unmatched = final_report[final_report['Customer Payment'].isna()]
                    if len(unmatched) > 0:
                        unmatched.to_excel(writer, sheet_name='Unmatched Records', index=False)
                
                st.download_button(
                    label="📥 Download All Reports (Excel)",
                    data=excel_buffer.getvalue(),
                    file_name=f"complete_reports_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            with col2:
                # Export consolidated report only
                csv_buffer = io.StringIO()
                final_report.to_csv(csv_buffer, index=False)
                st.download_button(
                    label="📥 Download Consolidated Report (CSV)",
                    data=csv_buffer.getvalue(),
                    file_name=f"consolidated_report_{timestamp}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with col3:
                # Export branch summary
                branch_summary = generator.generate_branch_summary_report(final_report)
                if len(branch_summary) > 0:
                    csv_buffer = io.StringIO()
                    branch_summary.to_csv(csv_buffer, index=False)
                    st.download_button(
                        label="📥 Download Branch Summary (CSV)",
                        data=csv_buffer.getvalue(),
                        file_name=f"branch_summary_{timestamp}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            st.info("Please check that your files have the correct column names and data formats.")
    
    else:
        st.info("👈 **Please upload all three files** (Employees, Referrals, and Transactions reports) to generate the consolidated report.")

if __name__ == "__main__":
    main()
