import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io
import re
from collections import defaultdict

class ReportGenerator:
    def __init__(self, employees_df, referrals_df, transactions_df, bss_df=None):
        self.employees_df = employees_df
        self.referrals_df = referrals_df
        self.transactions_df = transactions_df
        self.bss_df = bss_df
        
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

    def clean_currency_amount(self, amount):
        """
        Clean currency amount by removing ₹ symbol, commas, and converting to float
        Handles formats like: 'â‚¹2,800', '₹2,800', '2,800', '2800'
        """
        if pd.isna(amount):
            return np.nan
        
        # Convert to string
        amount_str = str(amount).strip()
        
        # Remove common currency symbols and special characters
        # Handle â‚¹ (which is ₹ in some encodings), ₹, Rs, etc.
        amount_str = re.sub(r'[^\d\-\.\,]', '', amount_str)  # Remove all except digits, dash, dot, comma
        amount_str = amount_str.replace(',', '')  # Remove commas
        
        # Convert to float
        try:
            return float(amount_str)
        except:
            return np.nan

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

    def match_with_bss_report(self, final_report):
        """
        Match remaining joined schemes with BSS Report
        Conditions:
        - Referral report Referee Phone + BSS Report Mobileno
        - Referral report Joined Date + BSS Report Date
        - Referral report Enrollment Amount + BSS Report Online
        """
        if self.bss_df is None or len(self.bss_df) == 0:
            st.warning("⚠️ BSS Report not provided. Some scheme details may remain unmatched.")
            return final_report
        
        st.info("🔍 Attempting to match remaining records with BSS Report...")
        
        # Prepare BSS data for matching
        bss_clean = self.bss_df.copy()
        
        # Check required columns in BSS report
        required_bss_cols = {
            'Mobileno': 'Customer Phone',
            'Date': 'Date',
            'Online': 'Online Amount',
            'Scheme': 'Scheme Name',
            'Doc No': 'Passbook Number'
        }
        
        missing_cols = []
        for bss_col in required_bss_cols.keys():
            if bss_col not in bss_clean.columns:
                missing_cols.append(bss_col)
        
        if missing_cols:
            st.warning(f"⚠️ BSS Report missing columns: {', '.join(missing_cols)}. Some columns may not be available for matching.")
        
        # Clean phone numbers in BSS
        if 'Mobileno' in bss_clean.columns:
            bss_clean['Clean Phone'] = bss_clean['Mobileno'].apply(self.clean_phone_number)
        else:
            st.error("❌ 'Mobileno' column not found in BSS Report")
            return final_report
        
        # Parse dates in BSS
        if 'Date' in bss_clean.columns:
            bss_clean['Clean Date'] = bss_clean['Date'].apply(self.parse_date_flexible)
        else:
            st.warning("⚠️ 'Date' column not found in BSS Report, using date matching without date validation")
            bss_clean['Clean Date'] = None
        
        # Convert Online amount to numeric (handle currency formatting)
        if 'Online' in bss_clean.columns:
            bss_clean['Online Amount'] = bss_clean['Online'].apply(self.clean_currency_amount)
        else:
            st.warning("⚠️ 'Online' column not found in BSS Report, amount matching will be skipped")
            bss_clean['Online Amount'] = np.nan
        
        # Create BSS lookup dictionary with composite key (store multiple matches)
        bss_lookup = defaultdict(list)
        for idx, row in bss_clean.iterrows():
            phone = row['Clean Phone']
            date = row['Clean Date']
            amount = row['Online Amount']
            
            if phone and phone != "":
                # Create key with phone only (more flexible)
                key = phone
                if date:
                    # If date is available, add to key for more precise matching
                    key = f"{phone}_{date}"
                
                # Store BSS record (allow multiple per key)
                bss_lookup[key].append({
                    'amount': amount,
                    'scheme_name': row.get('Scheme', ''),
                    'doc_no': row.get('Doc No', ''),
                    'date': date
                })
        
        # Find records that need BSS matching (joined schemes with empty payment/scheme name)
        need_bss_matching = final_report[
            (final_report['Not Enrolled'] == True) & 
            (final_report['Status'].str.lower().str.contains('joined', na=False))
        ].copy()
        
        st.info(f"📊 Found {len(need_bss_matching)} records that need BSS Report matching")
        
        if len(need_bss_matching) == 0:
            st.success("✅ No records need BSS matching")
            return final_report
        
        # Attempt to match each record with BSS
        matched_count = 0
        for idx in need_bss_matching.index:
            row = final_report.loc[idx]
            customer_phone = row['Customer Phone']
            updated_date = row['Updated Date']
            enrollment_amount = row['Customer Enrollment Amount']
            
            if not customer_phone or customer_phone == "":
                continue
            
            matched = False
            
            # Try to find match in BSS
            # First try with phone + date
            if pd.notna(updated_date):
                exact_key = f"{customer_phone}_{updated_date}"
                if exact_key in bss_lookup:
                    for match in bss_lookup[exact_key]:
                        # Check amount match if available
                        if pd.notna(enrollment_amount) and pd.notna(match['amount']):
                            if abs(match['amount'] - enrollment_amount) <= 1:  # Allow 1 rupee difference
                                # Match found
                                final_report.loc[idx, 'Customer Payment'] = match['amount']
                                final_report.loc[idx, 'Scheme Name'] = match['scheme_name']
                                final_report.loc[idx, 'Scheme Passbook Number'] = match['doc_no']
                                final_report.loc[idx, 'True/False'] = True
                                final_report.loc[idx, 'Not Enrolled'] = False
                                matched_count += 1
                                matched = True
                                break
                        else:
                            # If amount not available for matching, still match if phone and date match
                            final_report.loc[idx, 'Customer Payment'] = match['amount'] if pd.notna(match['amount']) else enrollment_amount
                            final_report.loc[idx, 'Scheme Name'] = match['scheme_name']
                            final_report.loc[idx, 'Scheme Passbook Number'] = match['doc_no']
                            final_report.loc[idx, 'True/False'] = True
                            final_report.loc[idx, 'Not Enrolled'] = False
                            matched_count += 1
                            matched = True
                            break
            
            # If no match with date, try with phone only (and match by amount)
            if not matched:
                phone_key = customer_phone
                if phone_key in bss_lookup:
                    # First try to find exact amount match
                    for match in bss_lookup[phone_key]:
                        if pd.notna(enrollment_amount) and pd.notna(match['amount']):
                            if abs(match['amount'] - enrollment_amount) <= 1:
                                final_report.loc[idx, 'Customer Payment'] = match['amount']
                                final_report.loc[idx, 'Scheme Name'] = match['scheme_name']
                                final_report.loc[idx, 'Scheme Passbook Number'] = match['doc_no']
                                final_report.loc[idx, 'True/False'] = True
                                final_report.loc[idx, 'Not Enrolled'] = False
                                matched_count += 1
                                matched = True
                                break
                    
                    # If no amount match, use first match as fallback
                    if not matched and len(bss_lookup[phone_key]) > 0:
                        match = bss_lookup[phone_key][0]
                        final_report.loc[idx, 'Customer Payment'] = match['amount'] if pd.notna(match['amount']) else enrollment_amount
                        final_report.loc[idx, 'Scheme Name'] = match['scheme_name']
                        final_report.loc[idx, 'Scheme Passbook Number'] = match['doc_no']
                        final_report.loc[idx, 'True/False'] = True
                        final_report.loc[idx, 'Not Enrolled'] = False
                        matched_count += 1
                        matched = True
        
        st.success(f"✅ Successfully matched {matched_count} records using BSS Report")
        
        # Show unmatched records count
        still_unmatched = final_report[
            (final_report['Not Enrolled'] == True) & 
            (final_report['Status'].str.lower().str.contains('joined', na=False))
        ].shape[0]
        
        if still_unmatched > 0:
            st.warning(f"⚠️ {still_unmatched} joined scheme records remain unmatched even after BSS matching")
        
        return final_report

    def generate_report(self):
        """Generate the final consolidated report"""
        
        # Create a copy of referrals report as base
        final_report = pd.DataFrame()
        
        # 1. Updated Date (Conditional based on Status)
        has_joined_date = 'Joined Date' in self.referrals_df.columns
        has_registered_date = 'Registered Date' in self.referrals_df.columns
        
        if has_joined_date or has_registered_date:
            final_report['Updated Date'] = self.referrals_df.apply(self.get_updated_date, axis=1)
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
            final_report['Customer Enrollment Amount'] = self.referrals_df['Enrollment Amount'].apply(self.clean_currency_amount)
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
        
        # 9. Employee Code (Match with Employees report) - MODIFIED TO HANDLE "NA" AS VALID VALUE
        if 'Referral Code' in self.employees_df.columns and 'Employee Code' in self.employees_df.columns:
            # Create dictionary for mapping - treat all values as strings, including "NA"
            emp_code_dict = {}
            for idx, row in self.employees_df.iterrows():
                referral_code = str(row['Referral Code']).strip()
                employee_code = str(row['Employee Code']).strip() if pd.notna(row['Employee Code']) else ''
                emp_code_dict[referral_code] = employee_code
            
            final_report['Employee Code'] = final_report['Referral Code'].astype(str).map(emp_code_dict)
            
            # Fill missing mappings with empty string (not NaN)
            final_report['Employee Code'] = final_report['Employee Code'].fillna('')
        else:
            st.warning("⚠️ 'Referral Code' or 'Employee Code' missing in Employees Report")
            final_report['Employee Code'] = ''
        
        # 10. Branch (Match with Employees report and apply transformation)
        if 'Referral Code' in self.employees_df.columns and 'Branch' in self.employees_df.columns:
            branch_dict = dict(zip(
                self.employees_df['Referral Code'].astype(str), 
                self.employees_df['Branch']
            ))
            final_report['Raw Branch'] = final_report['Referral Code'].astype(str).map(branch_dict)
            final_report['Branch'] = final_report['Raw Branch'].apply(self.transform_branch)
            final_report.drop('Raw Branch', axis=1, inplace=True)
            st.success("✅ Branch transformation logic applied successfully (Proper Case)")
        else:
            st.warning("⚠️ 'Referral Code' or 'Branch' missing in Employees Report")
            final_report['Branch'] = "Bhima Jewellery - Customer"
        
        # 15. Category (from Employee Type in EMPLOYEES report)
        if 'Referral Code' in self.employees_df.columns and 'Employee Type' in self.employees_df.columns:
            emp_type_dict = dict(zip(
                self.employees_df['Referral Code'].astype(str), 
                self.employees_df['Employee Type']
            ))
            final_report['Category'] = final_report['Referral Code'].astype(str).map(emp_type_dict)
            final_report['Category'] = final_report['Category'].fillna('Customer')
        else:
            st.warning("⚠️ 'Referral Code' or 'Employee Type' missing in Employees Report")
            final_report['Category'] = 'Customer'
        
        # Prepare transactions data for matching
        if 'Installment number' in self.transactions_df.columns:
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
        
        # Clean Saved Amount in transactions
        if 'Saved Amount' in trans_filtered.columns:
            trans_filtered['Saved Amount Clean'] = trans_filtered['Saved Amount'].apply(self.clean_currency_amount)
        else:
            st.warning("⚠️ 'Saved Amount' column not found in Transactions Report")
            trans_filtered['Saved Amount Clean'] = np.nan
        
        # Create lookup dictionary with multiple transactions per key
        trans_filtered['Match Key'] = trans_filtered['Clean Phone'] + "_" + trans_filtered['Paid Date Clean'].astype(str)
        
        # Store multiple transactions per key using defaultdict(list)
        transaction_lookup = defaultdict(list)
        for idx, row in trans_filtered.iterrows():
            key = row['Match Key']
            transaction_lookup[key].append({
                'saved_amount': row['Saved Amount Clean'] if 'Saved Amount Clean' in row else np.nan,
                'scheme_name': row.get('Scheme Name', '') if 'Scheme Name' in row else '',
                'passbook_no': row.get('Passbook number', '') if 'Passbook number' in row else ''
            })
        
        # Match Customer Payment, Scheme Name, Scheme Passbook Number with amount verification
        def get_transaction_details(row):
            customer_phone = row['Customer Phone']
            updated_date = row['Updated Date']
            enrollment_amount = row['Customer Enrollment Amount']
            
            if pd.isna(updated_date) or customer_phone == "":
                return np.nan, "", ""
            
            # Create match key
            match_key = customer_phone + "_" + str(updated_date)
            
            # Look up in dictionary
            if match_key in transaction_lookup:
                # First try to find transaction that matches the amount exactly
                for trans in transaction_lookup[match_key]:
                    if pd.notna(enrollment_amount) and pd.notna(trans['saved_amount']):
                        if abs(trans['saved_amount'] - enrollment_amount) <= 1:  # Allow 1 rupee difference
                            return trans['saved_amount'], trans['scheme_name'], trans['passbook_no']
                
                # If no exact amount match, return the first transaction
                first_trans = transaction_lookup[match_key][0]
                return first_trans['saved_amount'], first_trans['scheme_name'], first_trans['passbook_no']
            else:
                return np.nan, "", ""
        
        # Apply transaction matching
        transaction_details = final_report.apply(get_transaction_details, axis=1, result_type='expand')
        final_report['Customer Payment'] = transaction_details[0]
        final_report['Scheme Name'] = transaction_details[1]
        final_report['Scheme Passbook Number'] = transaction_details[2]
        
        # True/False (Compare Enrollment Amount with Customer Payment)
        final_report['True/False'] = np.where(
            final_report['Customer Enrollment Amount'] == final_report['Customer Payment'],
            True,
            False
        )
        
        # Clear Customer Payment, Scheme Name, and Scheme Passbook Number when True/False is False
        final_report.loc[final_report['True/False'] == False, 'Customer Payment'] = np.nan
        final_report.loc[final_report['True/False'] == False, 'Scheme Name'] = ''
        final_report.loc[final_report['True/False'] == False, 'Scheme Passbook Number'] = ''
        
        # Add Not Enrolled flag
        final_report['Not Enrolled'] = final_report['Customer Payment'].isna()
        
        # Match with BSS Report for remaining joined schemes
        final_report = self.match_with_bss_report(final_report)
        
        # Month (extract month name from Updated Date)
        final_report['Month'] = final_report['Updated Date'].apply(
            lambda x: x.strftime('%B').lower() if pd.notna(x) else ''
        )
        
        # Select final columns
        final_columns = [
            'Updated Date', 'Customer Name', 'Customer Phone', 'Customer Enrollment Amount',
            'Status', 'Employee Name', 'Referral Code', 'Employee Phone', 'Employee Code',
            'Branch', 'Customer Payment', 'True/False', 'Scheme Name', 'Scheme Passbook Number',
            'Category', 'Month', 'Not Enrolled'
        ]
        
        for col in final_columns:
            if col not in final_report.columns:
                final_report[col] = np.nan
        
        # Show statistics
        matched_count = final_report['Customer Payment'].notna().sum()
        not_enrolled_count = final_report['Not Enrolled'].sum()
        if len(final_report) > 0:
            st.info(f"📊 Final Match Results: {matched_count} out of {len(final_report)} records matched ({matched_count/len(final_report)*100:.1f}%)")
            st.info(f"📊 Not Enrolled Customers: {not_enrolled_count} out of {len(final_report)} ({not_enrolled_count/len(final_report)*100:.1f}%)")
        
        category_counts = final_report['Category'].value_counts()
        st.info(f"📊 Category Distribution: {dict(category_counts)}")
        
        branch_counts = final_report['Branch'].value_counts().head(10)
        st.info(f"📊 Top 10 Branches: {dict(branch_counts)}")
        
        return final_report[final_columns]

    def generate_branch_wise_scheme_report(self, final_report):
        """Generate Branch-wise Scheme Consolidation Report"""
        report_data = final_report[final_report['Scheme Name'].notna() & (final_report['Scheme Name'] != '')].copy()
        
        if len(report_data) == 0:
            return pd.DataFrame()
        
        branch_scheme_report = report_data.groupby(['Branch', 'Scheme Name']).agg({
            'Customer Name': 'count',
            'Customer Enrollment Amount': 'sum',
            'Customer Payment': 'sum',
            'True/False': 'sum',
            'Employee Name': 'nunique',
            'Referral Code': 'nunique'
        }).reset_index()
        
        branch_scheme_report.columns = [
            'Branch', 'Scheme Name', 'Number of Customers', 
            'Total Enrollment Amount', 'Total Payment Received', 
            'Number of Matched Payments', 'Unique Employees', 'Unique Referral Codes'
        ]
        
        branch_scheme_report['Match Rate (%)'] = (
            branch_scheme_report['Number of Matched Payments'] / 
            branch_scheme_report['Number of Customers'] * 100
        ).round(2)
        
        branch_scheme_report['Pending Amount'] = (
            branch_scheme_report['Total Enrollment Amount'] - 
            branch_scheme_report['Total Payment Received']
        )
        
        branch_scheme_report = branch_scheme_report.sort_values(['Branch', 'Number of Customers'], ascending=[True, False])
        
        return branch_scheme_report

    def generate_branch_employee_wise_scheme_report(self, final_report):
        """Generate Branch and Employee-wise Scheme Report"""
        # Ensure Employee Code is treated as string, preserving "NA" values
        report_data = final_report[final_report['Scheme Name'].notna() & (final_report['Scheme Name'] != '')].copy()
        report_data['Employee Code'] = report_data['Employee Code'].astype(str).fillna('')
        
        if len(report_data) == 0:
            return pd.DataFrame()
        
        emp_scheme_report = report_data.groupby(['Branch', 'Employee Name', 'Employee Code', 'Referral Code', 'Scheme Name']).agg({
            'Customer Name': 'count',
            'Customer Enrollment Amount': 'sum',
            'Customer Payment': 'sum',
            'True/False': 'sum',
            'Customer Phone': 'nunique'
        }).reset_index()
        
        emp_scheme_report.columns = [
            'Branch', 'Employee Name', 'Employee Code', 'Referral Code', 'Scheme Name',
            'Number of Customers', 'Total Enrollment Amount', 'Total Payment Received',
            'Number of Matched Payments', 'Unique Customers'
        ]
        
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
        
        emp_scheme_report = emp_scheme_report.sort_values(
            ['Branch', 'Employee Name', 'Number of Customers'], 
            ascending=[True, True, False]
        )
        
        return emp_scheme_report

    def generate_branch_summary_report(self, final_report):
        """Generate Branch-wise Summary Report"""
        branch_summary = final_report.groupby('Branch').agg({
            'Customer Name': 'count',
            'Customer Enrollment Amount': 'sum',
            'Customer Payment': 'sum',
            'True/False': 'sum',
            'Employee Name': 'nunique',
            'Referral Code': 'nunique',
            'Scheme Name': lambda x: x.notna().sum(),
            'Not Enrolled': 'sum'
        }).reset_index()
        
        branch_summary.columns = [
            'Branch', 'Total Customers', 'Total Enrollment Amount', 
            'Total Payment Received', 'Matched Payments', 'Unique Employees', 
            'Unique Referral Codes', 'Schemes Sold', 'Not Enrolled'
        ]
        
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
        
        branch_summary = branch_summary.sort_values('Total Customers', ascending=False)
        
        return branch_summary

    def generate_employee_performance_report(self, final_report):
        """Generate Employee Performance Report"""
        # Ensure Employee Code is treated as string, preserving "NA" values
        final_report_copy = final_report.copy()
        final_report_copy['Employee Code'] = final_report_copy['Employee Code'].astype(str).fillna('')
        
        emp_performance = final_report_copy.groupby(['Employee Name', 'Employee Code', 'Referral Code', 'Branch', 'Category']).agg({
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
        
        emp_performance = emp_performance.sort_values('Total Customers', ascending=False)
        
        return emp_performance

    def generate_registration_analysis_report(self, final_report):
        """Generate Registration Analysis Report"""
        reg_analysis = final_report.copy()
        
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
        
        branch_reg_summary = reg_analysis.groupby(['Branch', 'Registration Status']).agg({
            'Customer Name': 'count',
            'Customer Enrollment Amount': 'sum',
            'Customer Payment': 'sum',
            'Referral Code': 'nunique'
        }).reset_index()
        
        branch_reg_summary.columns = [
            'Branch', 'Registration Status', 'Customer Count', 
            'Total Enrollment Amount', 'Total Payment Received', 'Unique Referral Codes'
        ]
        
        branch_reg_pivot = branch_reg_summary.pivot_table(
            index='Branch',
            columns='Registration Status',
            values='Customer Count',
            fill_value=0
        ).reset_index()
        
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
        
        branch_reg_pivot = branch_reg_pivot.sort_values('Total Customers', ascending=False)
        
        not_enrolled_customers = final_report[final_report['Not Enrolled'] == True].copy()
        not_enrolled_customers = not_enrolled_customers[[
            'Customer Name', 'Customer Phone', 'Employee Name', 'Employee Code', 
            'Referral Code', 'Branch', 'Status', 'Customer Enrollment Amount', 'Updated Date'
        ]]
        
        return branch_reg_pivot, not_enrolled_customers

    def generate_branch_employee_referral_report(self, final_report, start_date=None, end_date=None):
        """Generate Branch & Employee-wise Referral Report with date filtering"""
        
        filtered_report = final_report.copy()
        # Ensure Employee Code is treated as string, preserving "NA" values
        filtered_report['Employee Code'] = filtered_report['Employee Code'].astype(str).fillna('')
        
        if start_date and end_date:
            filtered_report['Updated Date'] = pd.to_datetime(filtered_report['Updated Date'], errors='coerce')
            mask = (filtered_report['Updated Date'] >= pd.to_datetime(start_date)) & (filtered_report['Updated Date'] <= pd.to_datetime(end_date))
            filtered_report = filtered_report[mask]
        
        enrolled_data = filtered_report[filtered_report['Not Enrolled'] == False].copy()
        
        all_schemes = enrolled_data['Scheme Name'].dropna().unique()
        all_schemes = [s for s in all_schemes if s != '']
        all_schemes = sorted(all_schemes)
        
        if len(all_schemes) == 0:
            all_schemes = ['No Scheme']
        
        branch_summary = []
        branches = sorted(filtered_report['Branch'].unique())
        
        grand_totals = {
            'scheme_counts': {scheme: 0 for scheme in all_schemes},
            'scheme_amounts': {scheme: 0 for scheme in all_schemes},
            'total_enrolled_count': 0,
            'total_enrolled_amount': 0,
            'total_not_enrolled': 0
        }
        
        for branch in branches:
            branch_data = filtered_report[filtered_report['Branch'] == branch]
            branch_enrolled = branch_data[branch_data['Not Enrolled'] == False]
            
            branch_row = {
                'Branch': branch,
                'Not Enrolled Count': len(branch_data[branch_data['Not Enrolled'] == True])
            }
            
            branch_total_count = 0
            branch_total_amount = 0
            
            for scheme in all_schemes:
                scheme_data = branch_enrolled[branch_enrolled['Scheme Name'] == scheme]
                scheme_count = len(scheme_data)
                scheme_amount = scheme_data['Customer Enrollment Amount'].sum() if len(scheme_data) > 0 else 0
                
                scheme_count = int(scheme_count) if not pd.isna(scheme_count) else 0
                scheme_amount = float(scheme_amount) if not pd.isna(scheme_amount) else 0
                
                branch_row[f'{scheme} Count'] = scheme_count
                branch_row[f'{scheme} Amount'] = scheme_amount
                
                branch_total_count += scheme_count
                branch_total_amount += scheme_amount
                
                grand_totals['scheme_counts'][scheme] += scheme_count
                grand_totals['scheme_amounts'][scheme] += scheme_amount
            
            branch_row['Total Enrolled Count'] = branch_total_count
            branch_row['Total Enrolled Amount'] = branch_total_amount
            
            grand_totals['total_enrolled_count'] += branch_total_count
            grand_totals['total_enrolled_amount'] += branch_total_amount
            grand_totals['total_not_enrolled'] += branch_row['Not Enrolled Count']
            
            branch_summary.append(branch_row)
        
        branch_df = pd.DataFrame(branch_summary)
        
        if grand_totals['total_enrolled_count'] > 0:
            branch_df['Count %'] = (branch_df['Total Enrolled Count'] / grand_totals['total_enrolled_count'] * 100).round(0).astype(int).astype(str) + '%'
        else:
            branch_df['Count %'] = '0%'
            
        if grand_totals['total_enrolled_amount'] > 0:
            branch_df['Amount %'] = (branch_df['Total Enrolled Amount'] / grand_totals['total_enrolled_amount'] * 100).round(0).astype(int).astype(str) + '%'
        else:
            branch_df['Amount %'] = '0%'
        
        grand_total_row = {'Branch': 'Grand Total'}
        for scheme in all_schemes:
            grand_total_row[f'{scheme} Count'] = grand_totals['scheme_counts'][scheme]
            grand_total_row[f'{scheme} Amount'] = grand_totals['scheme_amounts'][scheme]
        
        grand_total_row['Total Enrolled Count'] = grand_totals['total_enrolled_count']
        grand_total_row['Total Enrolled Amount'] = grand_totals['total_enrolled_amount']
        grand_total_row['Not Enrolled Count'] = grand_totals['total_not_enrolled']
        grand_total_row['Count %'] = '100%'
        grand_total_row['Amount %'] = '100%'
        
        branch_df = pd.concat([branch_df, pd.DataFrame([grand_total_row])], ignore_index=True)
        
        amount_columns = [col for col in branch_df.columns if 'Amount' in col and col != 'Amount %']
        for col in amount_columns:
            branch_df[col] = pd.to_numeric(branch_df[col], errors='coerce').fillna(0)
            branch_df[col] = branch_df[col].apply(lambda x: f"₹{x:,.0f}" if x > 0 else "-")
        
        employee_details = []
        
        for branch in branches:
            branch_data = filtered_report[filtered_report['Branch'] == branch]
            branch_enrolled = branch_data[branch_data['Not Enrolled'] == False]
            
            employees_with_enrolled = branch_enrolled['Employee Name'].dropna().unique()
            not_enrolled_employees = branch_data[branch_data['Not Enrolled'] == True]['Employee Name'].dropna().unique()
            all_employees = list(set(list(employees_with_enrolled) + list(not_enrolled_employees)))
            
            if len(all_employees) == 0 and len(branch_enrolled) == 0:
                emp_row = {
                    'Branch': branch,
                    'Employee Name': '',
                    'Employee Code': '',
                    'Referral Code': '',
                    'Total Enrolled Count': 0,
                    'Total Enrolled Amount': 0,
                    'Not Enrolled Count': len(branch_data[branch_data['Not Enrolled'] == True])
                }
                for scheme in all_schemes:
                    emp_row[f'{scheme} Count'] = 0
                    emp_row[f'{scheme} Amount'] = 0
                employee_details.append(emp_row)
            else:
                for employee in all_employees:
                    emp_data = branch_data[branch_data['Employee Name'] == employee]
                    emp_enrolled = emp_data[emp_data['Not Enrolled'] == False]
                    
                    emp_code = emp_data['Employee Code'].iloc[0] if len(emp_data) > 0 and pd.notna(emp_data['Employee Code'].iloc[0]) else ''
                    referral_code = emp_data['Referral Code'].iloc[0] if len(emp_data) > 0 and pd.notna(emp_data['Referral Code'].iloc[0]) else ''
                    
                    employee_row = {
                        'Branch': branch,
                        'Employee Name': employee if employee and str(employee) != 'nan' else 'Unassigned',
                        'Employee Code': str(emp_code) if emp_code else '',
                        'Referral Code': str(referral_code) if referral_code else '',
                    }
                    
                    emp_total_count = 0
                    emp_total_amount = 0
                    
                    for scheme in all_schemes:
                        scheme_data = emp_enrolled[emp_enrolled['Scheme Name'] == scheme]
                        scheme_count = len(scheme_data)
                        scheme_amount = scheme_data['Customer Enrollment Amount'].sum() if len(scheme_data) > 0 else 0
                        
                        scheme_count = int(scheme_count) if not pd.isna(scheme_count) else 0
                        scheme_amount = float(scheme_amount) if not pd.isna(scheme_amount) else 0
                        
                        employee_row[f'{scheme} Count'] = scheme_count
                        employee_row[f'{scheme} Amount'] = scheme_amount
                        
                        emp_total_count += scheme_count
                        emp_total_amount += scheme_amount
                    
                    employee_row['Total Enrolled Count'] = emp_total_count
                    employee_row['Total Enrolled Amount'] = emp_total_amount
                    employee_row['Not Enrolled Count'] = len(emp_data[emp_data['Not Enrolled'] == True])
                    
                    employee_details.append(employee_row)
                
                unassigned_data = branch_enrolled[branch_enrolled['Employee Name'].isna()]
                if len(unassigned_data) > 0:
                    unassigned_row = {
                        'Branch': branch,
                        'Employee Name': 'Unassigned',
                        'Employee Code': '',
                        'Referral Code': '',
                    }
                    
                    unassigned_total_count = 0
                    unassigned_total_amount = 0
                    
                    for scheme in all_schemes:
                        scheme_data = unassigned_data[unassigned_data['Scheme Name'] == scheme]
                        scheme_count = len(scheme_data)
                        scheme_amount = scheme_data['Customer Enrollment Amount'].sum() if len(scheme_data) > 0 else 0
                        
                        scheme_count = int(scheme_count) if not pd.isna(scheme_count) else 0
                        scheme_amount = float(scheme_amount) if not pd.isna(scheme_amount) else 0
                        
                        unassigned_row[f'{scheme} Count'] = scheme_count
                        unassigned_row[f'{scheme} Amount'] = scheme_amount
                        
                        unassigned_total_count += scheme_count
                        unassigned_total_amount += scheme_amount
                    
                    unassigned_row['Total Enrolled Count'] = unassigned_total_count
                    unassigned_row['Total Enrolled Amount'] = unassigned_total_amount
                    unassigned_row['Not Enrolled Count'] = 0
                    
                    employee_details.append(unassigned_row)
        
        employee_df = pd.DataFrame(employee_details)
        
        if len(employee_df) > 0:
            employee_df = employee_df.sort_values(['Branch', 'Total Enrolled Count'], ascending=[True, False])
        
        amount_columns = [col for col in employee_df.columns if 'Amount' in col and col != 'Amount %']
        for col in amount_columns:
            if col in employee_df.columns:
                employee_df[col] = pd.to_numeric(employee_df[col], errors='coerce').fillna(0)
                employee_df[col] = employee_df[col].apply(lambda x: f"₹{x:,.0f}" if x > 0 else "-")
        
        return branch_df, employee_df, all_schemes

def create_excel_report(final_report, generator, start_date=None, end_date=None):
    """Create Excel file with all reports"""
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
        
        reg_pivot, not_enrolled = generator.generate_registration_analysis_report(final_report)
        if len(reg_pivot) > 0:
            reg_pivot.to_excel(writer, sheet_name='Registration Analysis', index=False)
        if len(not_enrolled) > 0:
            not_enrolled.to_excel(writer, sheet_name='Not Enrolled Customers', index=False)
        
        branch_ref, employee_ref, _ = generator.generate_branch_employee_referral_report(final_report, start_date, end_date)
        if len(branch_ref) > 0:
            branch_ref.to_excel(writer, sheet_name='Branch Referral Summary', index=False)
        if len(employee_ref) > 0:
            employee_ref.to_excel(writer, sheet_name='Employee Referral Details', index=False)
    
    return excel_buffer

def get_week_number(date):
    """Get week number and year for a given date"""
    if pd.isna(date):
        return None
    try:
        date_obj = pd.to_datetime(date)
        week_num = date_obj.isocalendar()[1]
        year = date_obj.year
        return f"{year}-W{week_num:02d}"
    except:
        return None

def get_month_name(date):
    """Get month name and year for a given date"""
    if pd.isna(date):
        return None
    try:
        date_obj = pd.to_datetime(date)
        return date_obj.strftime('%B %Y')
    except:
        return None

def main():
    # Enhanced Custom CSS for better UI
    st.set_page_config(
        page_title="Report Generator System", 
        layout="wide",
        page_icon="📊",
        initial_sidebar_state="collapsed"
    )
    
    # Custom CSS for better styling
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .main-header h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 600;
    }
    
    .main-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.9;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        color: white;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .metric-card h3 {
        margin: 0;
        font-size: 0.9rem;
        opacity: 0.9;
    }
    
    .metric-card .value {
        font-size: 1.8rem;
        font-weight: bold;
        margin: 0.5rem 0;
    }
    
    .success-box {
        background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%);
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .warning-box {
        background: linear-gradient(135deg, #ffe259 0%, #ffa751 100%);
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .info-box {
        background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .error-box {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        color: white;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #f8f9fa;
        padding: 0.5rem;
        border-radius: 10px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background-color: #e9ecef;
        transform: translateY(-2px);
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white !important;
    }
    
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
    }
    
    .uploadedFile {
        border-radius: 10px;
        border: 2px dashed #ddd;
        background-color: #f8f9fa;
    }
    
    .dataframe {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .css-1d391kg {
        background-color: #f8f9fa;
    }
    
    .stProgress > div > div {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    @keyframes fadeIn {
        from {
            opacity: 0;
            transform: translateY(-10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .success-box, .warning-box, .info-box, .error-box {
        animation: fadeIn 0.5s ease-out;
    }
    
    .download-buttons {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin: 20px 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Main header with gradient
    st.markdown("""
    <div class="main-header">
        <h1>📊 Automated Report Generator</h1>
        <p>Generate consolidated reports from Employees, Referrals, Transactions, and BSS data</p>
    </div>
    """, unsafe_allow_html=True)
    
    # File upload section with better layout
    st.markdown("### 📁 Upload Your Files")
    st.markdown("---")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        with st.container():
            st.markdown("**📋 Employees Report**")
            employees_file = st.file_uploader(
                "",
                type=['xlsx', 'xls', 'csv'],
                help="Upload Excel or CSV file containing employee data",
                key="emp_file",
                label_visibility="collapsed"
            )
            if employees_file:
                st.success("✅ Uploaded")
            else:
                st.info("Required")
    
    with col2:
        with st.container():
            st.markdown("**👥 Referrals Report**")
            referrals_file = st.file_uploader(
                "",
                type=['xlsx', 'xls', 'csv'],
                help="Upload Excel or CSV file containing referral data",
                key="ref_file",
                label_visibility="collapsed"
            )
            if referrals_file:
                st.success("✅ Uploaded")
            else:
                st.info("Required")
    
    with col3:
        with st.container():
            st.markdown("**💰 Transactions Report**")
            transactions_file = st.file_uploader(
                "",
                type=['xlsx', 'xls', 'csv'],
                help="Upload Excel or CSV file containing transaction data",
                key="trans_file",
                label_visibility="collapsed"
            )
            if transactions_file:
                st.success("✅ Uploaded")
            else:
                st.info("Required")
    
    with col4:
        with st.container():
            st.markdown("**📑 BSS Report (Optional)**")
            bss_file = st.file_uploader(
                "",
                type=['xlsx', 'xls', 'csv'],
                help="Upload BSS Excel or CSV file for additional matching",
                key="bss_file",
                label_visibility="collapsed"
            )
            if bss_file:
                st.success("✅ Uploaded")
            else:
                st.info("Optional")
    
    st.markdown("---")
    
    # Process files when required files are uploaded
    if employees_file and referrals_file and transactions_file:
        try:
            # Load files with progress indicator
            with st.spinner("📂 Loading files..."):
                progress_bar = st.progress(0)
                
                # Load Employees Report - MODIFIED to preserve "NA" as string value
                if employees_file.name.endswith('.csv'):
                    employees_df = pd.read_csv(employees_file, keep_default_na=False, na_values=[])
                else:
                    employees_df = pd.read_excel(employees_file, keep_default_na=False, na_values=[])
                progress_bar.progress(25)
                
                # Load Referrals Report
                if referrals_file.name.endswith('.csv'):
                    referrals_df = pd.read_csv(referrals_file, keep_default_na=False, na_values=[])
                else:
                    referrals_df = pd.read_excel(referrals_file, keep_default_na=False, na_values=[])
                progress_bar.progress(50)
                
                # Load Transactions Report
                if transactions_file.name.endswith('.csv'):
                    transactions_df = pd.read_csv(transactions_file, keep_default_na=False, na_values=[])
                else:
                    transactions_df = pd.read_excel(transactions_file, keep_default_na=False, na_values=[])
                progress_bar.progress(75)
                
                # Load BSS Report if provided
                bss_df = None
                if bss_file:
                    if bss_file.name.endswith('.csv'):
                        bss_df = pd.read_csv(bss_file, keep_default_na=False, na_values=[])
                    else:
                        bss_df = pd.read_excel(bss_file, keep_default_na=False, na_values=[])
                    st.success(f"✅ BSS Report loaded with {len(bss_df):,} records")
                progress_bar.progress(100)
                
                progress_bar.empty()
            
            # Check for required date columns in referrals
            has_joined_date = 'Joined Date' in referrals_df.columns
            has_registered_date = 'Registered Date' in referrals_df.columns
            
            if not has_joined_date and not has_registered_date:
                st.markdown('<div class="error-box">❌ Referrals Report must contain either "Joined Date" or "Registered Date" column</div>', unsafe_allow_html=True)
                st.stop()
            
            # Generate report
            with st.spinner("🔄 Generating consolidated report..."):
                generator = ReportGenerator(employees_df, referrals_df, transactions_df, bss_df)
                final_report = generator.generate_report()
                
                if final_report is None:
                    st.markdown('<div class="error-box">❌ Failed to generate report. Please check your data.</div>', unsafe_allow_html=True)
                    st.stop()
            
            # Display success message
            st.markdown('<div class="success-box">✅ Report generated successfully!</div>', unsafe_allow_html=True)
            
            # Add date range filter section
            st.markdown("---")
            st.markdown("### 📅 Date Range Filter for Reports")
            st.markdown("Apply filters to view data for specific time periods")
            
            # Create columns for date filter controls
            col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
            
            # Initialize filter variables
            filter_start_date = None
            filter_end_date = None
            apply_filter = False
            
            with col1:
                start_date = st.date_input("Start Date", value=None, key="global_start_date")
            with col2:
                end_date = st.date_input("End Date", value=None, key="global_end_date")
            with col3:
                # Add week selection
                if 'Updated Date' in final_report.columns:
                    # Create week options from data
                    final_report['Week Number'] = final_report['Updated Date'].apply(get_week_number)
                    unique_weeks = sorted([w for w in final_report['Week Number'].unique() if w is not None], reverse=True)
                    week_options = ['All'] + unique_weeks
                    selected_week = st.selectbox("Select Week", week_options, key="week_select")
                    
                    # Auto-populate dates when week is selected
                    if selected_week != 'All' and selected_week in unique_weeks:
                        # Find the week's date range
                        week_data = final_report[final_report['Week Number'] == selected_week]
                        if len(week_data) > 0:
                            min_date = week_data['Updated Date'].min()
                            max_date = week_data['Updated Date'].max()
                            if pd.notna(min_date) and pd.notna(max_date):
                                start_date = min_date.date() if hasattr(min_date, 'date') else min_date
                                end_date = max_date.date() if hasattr(max_date, 'date') else max_date
                                st.rerun()
            with col4:
                # Add month selection
                if 'Updated Date' in final_report.columns:
                    final_report['Month Name'] = final_report['Updated Date'].apply(get_month_name)
                    unique_months = sorted([m for m in final_report['Month Name'].unique() if m is not None], reverse=True)
                    month_options = ['All'] + unique_months
                    selected_month = st.selectbox("Select Month", month_options, key="month_select")
                    
                    # Auto-populate dates when month is selected
                    if selected_month != 'All' and selected_month in unique_months:
                        month_data = final_report[final_report['Month Name'] == selected_month]
                        if len(month_data) > 0:
                            min_date = month_data['Updated Date'].min()
                            max_date = month_data['Updated Date'].max()
                            if pd.notna(min_date) and pd.notna(max_date):
                                start_date = min_date.date() if hasattr(min_date, 'date') else min_date
                                end_date = max_date.date() if hasattr(max_date, 'date') else max_date
                                st.rerun()
            
            # Apply filter button
            col5, col6, col7, col8 = st.columns([1, 1, 1, 1])
            with col5:
                apply_button = st.button("🔍 Apply Date Filter", use_container_width=False)
                if apply_button:
                    apply_filter = True
            
            with col6:
                clear_button = st.button("🗑️ Clear Filters", use_container_width=False)
                if clear_button:
                    start_date = None
                    end_date = None
                    selected_week = 'All'
                    selected_month = 'All'
                    apply_filter = False
                    st.rerun()
            
            # Use filtered dates if apply button clicked
            if apply_filter and start_date and end_date:
                filter_start_date = start_date
                filter_end_date = end_date
            
            # Show current filter status
            if filter_start_date and filter_end_date:
                filtered_data = final_report[
                    (pd.to_datetime(final_report['Updated Date']) >= pd.to_datetime(filter_start_date)) &
                    (pd.to_datetime(final_report['Updated Date']) <= pd.to_datetime(filter_end_date))
                ]
                st.success(f"✅ Filter applied: {filter_start_date} to {filter_end_date} - Showing {len(filtered_data)} records")
            else:
                st.info("ℹ️ No date filter applied - showing all data")
                filtered_data = final_report
            
            st.markdown("---")
            
            # Create tabs with icons for different reports
            tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
                "📋 **Consolidated Report**", 
                "🏢 **Branch-wise Scheme**", 
                "👥 **Branch & Employee Scheme**",
                "📊 **Branch Summary**",
                "⭐ **Employee Performance**",
                "📝 **Registration Analysis**",
                "📈 **Branch & Employee Referral**"
            ])
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            with tab1:
                st.markdown("### 📈 Final Consolidated Report")
                display_report = filtered_data.copy()
                st.dataframe(display_report, use_container_width=True, height=400)
                
                # Statistics with enhanced styling
                st.markdown("### 📊 Report Statistics")
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                
                with col1:
                    st.markdown("""
                    <div class="metric-card">
                        <h3>Total Records</h3>
                        <div class="value">{:,}</div>
                    </div>
                    """.format(len(display_report)), unsafe_allow_html=True)
                
                with col2:
                    total_amount = display_report['Customer Enrollment Amount'].sum()
                    st.markdown("""
                    <div class="metric-card">
                        <h3>Total Enrollment Amount</h3>
                        <div class="value">₹{:,.0f}</div>
                    </div>
                    """.format(total_amount if pd.notna(total_amount) else 0), unsafe_allow_html=True)
                
                with col3:
                    total_payment = display_report['Customer Payment'].sum()
                    st.markdown("""
                    <div class="metric-card">
                        <h3>Total Payments</h3>
                        <div class="value">₹{:,.0f}</div>
                    </div>
                    """.format(total_payment if pd.notna(total_payment) else 0), unsafe_allow_html=True)
                
                with col4:
                    matched = display_report['True/False'].sum() if 'True/False' in display_report.columns else 0
                    st.markdown("""
                    <div class="metric-card">
                        <h3>Matched Records</h3>
                        <div class="value">{:,}</div>
                    </div>
                    """.format(int(matched)), unsafe_allow_html=True)
                
                with col5:
                    match_percent = (matched / len(display_report) * 100) if len(display_report) > 0 else 0
                    st.markdown("""
                    <div class="metric-card">
                        <h3>Match Rate</h3>
                        <div class="value">{:.1f}%</div>
                    </div>
                    """.format(match_percent), unsafe_allow_html=True)
                
                with col6:
                    not_enrolled = display_report['Not Enrolled'].sum() if 'Not Enrolled' in display_report.columns else 0
                    st.markdown("""
                    <div class="metric-card">
                        <h3>Not Enrolled</h3>
                        <div class="value">{:,}</div>
                    </div>
                    """.format(int(not_enrolled)), unsafe_allow_html=True)
                
                # Individual download button for Consolidated Report
                st.markdown("#### 💾 Download This Report")
                csv_buffer = io.StringIO()
                display_report.to_csv(csv_buffer, index=False)
                st.download_button(
                    label="📥 Download Consolidated Report (CSV)",
                    data=csv_buffer.getvalue(),
                    file_name=f"consolidated_report_{timestamp}.csv",
                    mime="text/csv",
                    use_container_width=False
                )
            
            with tab2:
                st.markdown("### 🏢 Branch-wise Scheme Consolidation Report")
                branch_scheme_report = generator.generate_branch_wise_scheme_report(filtered_data)
                
                if len(branch_scheme_report) > 0:
                    col1, col2 = st.columns(2)
                    with col1:
                        branches = ['All'] + sorted(branch_scheme_report['Branch'].unique().tolist())
                        selected_branch = st.selectbox("🏢 Filter by Branch", branches, key="branch_scheme_filter")
                    
                    with col2:
                        schemes = ['All'] + sorted(branch_scheme_report['Scheme Name'].unique().tolist())
                        selected_scheme = st.selectbox("📋 Filter by Scheme", schemes, key="scheme_filter")
                    
                    filtered_report_data = branch_scheme_report.copy()
                    if selected_branch != 'All':
                        filtered_report_data = filtered_report_data[filtered_report_data['Branch'] == selected_branch]
                    if selected_scheme != 'All':
                        filtered_report_data = filtered_report_data[filtered_report_data['Scheme Name'] == selected_scheme]
                    
                    st.dataframe(filtered_report_data, use_container_width=True)
                    
                    # Individual download button for Branch-wise Scheme Report
                    st.markdown("#### 💾 Download This Report")
                    csv_buffer = io.StringIO()
                    filtered_report_data.to_csv(csv_buffer, index=False)
                    st.download_button(
                        label="📥 Download Branch-wise Scheme Report (CSV)",
                        data=csv_buffer.getvalue(),
                        file_name=f"branch_wise_scheme_{timestamp}.csv",
                        mime="text/csv",
                        use_container_width=False
                    )
                else:
                    st.info("ℹ️ No scheme data available")
            
            with tab3:
                st.markdown("### 👥 Branch & Employee-wise Scheme Report")
                emp_scheme_report = generator.generate_branch_employee_wise_scheme_report(filtered_data)
                
                if len(emp_scheme_report) > 0:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        branches = ['All'] + sorted(emp_scheme_report['Branch'].unique().tolist())
                        selected_branch = st.selectbox("🏢 Filter by Branch", branches, key="emp_branch_filter")
                    
                    with col2:
                        if selected_branch != 'All':
                            employees = ['All'] + sorted(emp_scheme_report[emp_scheme_report['Branch'] == selected_branch]['Employee Name'].unique().tolist())
                        else:
                            employees = ['All'] + sorted(emp_scheme_report['Employee Name'].unique().tolist())
                        selected_employee = st.selectbox("👤 Filter by Employee", employees, key="emp_filter")
                    
                    with col3:
                        schemes = ['All'] + sorted(emp_scheme_report['Scheme Name'].unique().tolist())
                        selected_scheme = st.selectbox("📋 Filter by Scheme", schemes, key="emp_scheme_filter")
                    
                    filtered_report_data = emp_scheme_report.copy()
                    if selected_branch != 'All':
                        filtered_report_data = filtered_report_data[filtered_report_data['Branch'] == selected_branch]
                    if selected_employee != 'All':
                        filtered_report_data = filtered_report_data[filtered_report_data['Employee Name'] == selected_employee]
                    if selected_scheme != 'All':
                        filtered_report_data = filtered_report_data[filtered_report_data['Scheme Name'] == selected_scheme]
                    
                    display_columns = ['Branch', 'Employee Name', 'Employee Code', 'Referral Code', 'Scheme Name',
                                      'Number of Customers', 'Total Enrollment Amount', 'Match Rate (%)']
                    st.dataframe(filtered_report_data[display_columns], use_container_width=True)
                    
                    # Individual download button for Branch-Employee Scheme Report
                    st.markdown("#### 💾 Download This Report")
                    csv_buffer = io.StringIO()
                    filtered_report_data[display_columns].to_csv(csv_buffer, index=False)
                    st.download_button(
                        label="📥 Download Branch-Employee Scheme Report (CSV)",
                        data=csv_buffer.getvalue(),
                        file_name=f"branch_employee_scheme_{timestamp}.csv",
                        mime="text/csv",
                        use_container_width=False                    )
                else:
                    st.info("ℹ️ No employee scheme data available")
            
            with tab4:
                st.markdown("### 📊 Branch Summary Report")
                branch_summary = generator.generate_branch_summary_report(filtered_data)
                
                if len(branch_summary) > 0:
                    st.dataframe(branch_summary, use_container_width=True)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("#### Top 10 Branches by Customers")
                        top_branches = branch_summary.head(10)
                        st.bar_chart(top_branches.set_index('Branch')['Total Customers'])
                    with col2:
                        st.markdown("#### Enrollment Rate by Branch")
                        st.bar_chart(top_branches.set_index('Branch')['Enrollment Rate (%)'])
                    
                    # Individual download button for Branch Summary Report
                    st.markdown("#### 💾 Download This Report")
                    csv_buffer = io.StringIO()
                    branch_summary.to_csv(csv_buffer, index=False)
                    st.download_button(
                        label="📥 Download Branch Summary Report (CSV)",
                        data=csv_buffer.getvalue(),
                        file_name=f"branch_summary_{timestamp}.csv",
                        mime="text/csv",
                        use_container_width=False
                    )
                else:
                    st.info("ℹ️ No branch summary data available")
            
            with tab5:
                st.markdown("### ⭐ Employee Performance Report")
                emp_performance = generator.generate_employee_performance_report(filtered_data)
                
                if len(emp_performance) > 0:
                    col1, col2 = st.columns(2)
                    with col1:
                        categories = ['All'] + sorted(emp_performance['Category'].unique().tolist())
                        selected_category = st.selectbox("🏷️ Filter by Category", categories)
                    
                    with col2:
                        branches = ['All'] + sorted(emp_performance['Branch'].unique().tolist())
                        selected_branch = st.selectbox("🏢 Filter by Branch", branches, key="perf_branch_filter")
                    
                    filtered_performance = emp_performance.copy()
                    if selected_category != 'All':
                        filtered_performance = filtered_performance[filtered_performance['Category'] == selected_category]
                    if selected_branch != 'All':
                        filtered_performance = filtered_performance[filtered_performance['Branch'] == selected_branch]
                    
                    display_columns = ['Employee Name', 'Referral Code', 'Branch', 'Total Customers', 
                                      'Total Enrollment Amount', 'Enrollment Rate (%)', 'Match Rate (%)']
                    st.dataframe(filtered_performance[display_columns], use_container_width=True)
                    
                    # Individual download button for Employee Performance Report
                    st.markdown("#### 💾 Download This Report")
                    csv_buffer = io.StringIO()
                    filtered_performance[display_columns].to_csv(csv_buffer, index=False)
                    st.download_button(
                        label="📥 Download Employee Performance Report (CSV)",
                        data=csv_buffer.getvalue(),
                        file_name=f"employee_performance_{timestamp}.csv",
                        mime="text/csv",
                        use_container_width=False
                    )
                else:
                    st.info("ℹ️ No employee performance data available")
            
            with tab6:
                st.markdown("### 📝 Registration Analysis Report")
                reg_pivot, not_enrolled_customers = generator.generate_registration_analysis_report(filtered_data)
                
                st.markdown("#### Registration Summary")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Customers", f"{len(filtered_data):,}")
                with col2:
                    enrolled = len(filtered_data[filtered_data['Not Enrolled'] == False])
                    st.metric("Enrolled", f"{enrolled:,}")
                with col3:
                    st.metric("Not Enrolled", f"{len(not_enrolled_customers):,}")
                with col4:
                    enrollment_rate = (enrolled/len(filtered_data)*100) if len(filtered_data) > 0 else 0
                    st.metric("Enrollment Rate", f"{enrollment_rate:.1f}%")
                
                st.markdown("#### Branch-wise Registration Status")
                st.dataframe(reg_pivot, use_container_width=True)
                
                # Individual download button for Registration Analysis
                st.markdown("#### 💾 Download Registration Analysis")
                csv_buffer = io.StringIO()
                reg_pivot.to_csv(csv_buffer, index=False)
                st.download_button(
                    label="📥 Download Registration Analysis Report (CSV)",
                    data=csv_buffer.getvalue(),
                    file_name=f"registration_analysis_{timestamp}.csv",
                    mime="text/csv",
                    use_container_width=False
                )
                
                if len(not_enrolled_customers) > 0:
                    st.markdown("#### Not Enrolled Customers")
                    st.dataframe(not_enrolled_customers, use_container_width=True)
                    
                    # Individual download button for Not Enrolled Customers
                    csv_buffer = io.StringIO()
                    not_enrolled_customers.to_csv(csv_buffer, index=False)
                    st.download_button(
                        label="📥 Download Not Enrolled Customers Report (CSV)",
                        data=csv_buffer.getvalue(),
                        file_name=f"not_enrolled_customers_{timestamp}.csv",
                        mime="text/csv",
                        use_container_width=False
                    )
            
            with tab7:
                st.markdown("### 📈 Branch & Employee Wise Referral Report")
                st.markdown("Shows branch and employee-wise scheme distribution for ALL schemes")
                
                branch_df, employee_df, schemes = generator.generate_branch_employee_referral_report(
                    filtered_data, 
                    filter_start_date, 
                    filter_end_date
                )
                
                if len(branch_df) > 0:
                    st.info(f"📊 **Schemes found:** {', '.join(schemes)}")
                    
                    # Create a single branch filter that controls both sections
                    st.markdown("#### 🔍 Filter by Branch (Applies to both sections below)")
                    
                    all_branches = sorted(branch_df[branch_df['Branch'] != 'Grand Total']['Branch'].unique().tolist())
                    
                    # Add "Select All" option for branches
                    branch_options = ['Select All'] + all_branches
                    selected_branches = st.multiselect(
                        "🏢 Select Branches",
                        options=branch_options,
                        default=['Select All'],
                        key="branch_ref_filter_sync"
                    )
                    
                    # Handle "Select All" selection
                    if 'Select All' in selected_branches:
                        selected_branches = all_branches
                    
                    # If no branches selected, show message
                    if not selected_branches:
                        st.warning("⚠️ Please select at least one branch to view data")
                    else:
                        # Filter branch_df based on selected branches
                        filtered_branch_df = branch_df[
                            (branch_df['Branch'].isin(selected_branches)) | 
                            (branch_df['Branch'] == 'Grand Total')
                        ].copy()
                        
                        # Filter employee_df based on selected branches
                        filtered_employee_df = employee_df[employee_df['Branch'].isin(selected_branches)].copy()
                        
                        st.markdown("#### Branch-wise Summary")
                        st.dataframe(filtered_branch_df, use_container_width=True)
                        
                        st.markdown("#### Employee-wise Details")
                        
                        if len(filtered_employee_df) > 0:
                            # Employee filter (independent, but only shows employees from selected branches)
                            available_employees = sorted(filtered_employee_df['Employee Name'].unique().tolist())
                            
                            # Add "Select All" option for employees
                            employee_options = ['Select All'] + available_employees
                            selected_employee_names = st.multiselect(
                                "👤 Filter by Employees (Optional - Multiple)",
                                options=employee_options,
                                default=[],
                                key="emp_ref_emp_sync"
                            )
                            
                            # Handle "Select All" selection
                            if 'Select All' in selected_employee_names:
                                selected_employee_names = [emp for emp in available_employees if emp != 'Select All']
                            
                            # Further filter by selected employees
                            if selected_employee_names:
                                filtered_employee_df = filtered_employee_df[filtered_employee_df['Employee Name'].isin(selected_employee_names)]
                            
                            # Display filtered employee data
                            st.dataframe(filtered_employee_df, use_container_width=True)
                            
                            # Summary statistics for selected branches - FIXED VERSION
                            st.markdown("#### 📊 Summary for Selected Branches")
                            col_a, col_b, col_c, col_d = st.columns(4)
                            
                            # Calculate totals from branch-level data (excluding Grand Total row)
                            branch_data = filtered_branch_df[filtered_branch_df['Branch'] != 'Grand Total'].copy()
                            
                            with col_a:
                                # Number of branches selected
                                total_branches = len(branch_data)
                                st.metric("Selected Branches", total_branches)
                            
                            with col_b:
                                # Calculate total enrolled from numeric columns only
                                total_enrolled = 0
                                if 'Total Enrolled Count' in branch_data.columns:
                                    # Convert to numeric, replacing any non-numeric with 0
                                    total_enrolled = pd.to_numeric(branch_data['Total Enrolled Count'], errors='coerce').fillna(0).sum()
                                st.metric("Total Enrolled", f"{int(total_enrolled):,}")
                            
                            with col_c:
                                # Calculate total not enrolled from numeric columns only
                                total_not_enrolled = 0
                                if 'Not Enrolled Count' in branch_data.columns:
                                    # Convert to numeric, replacing any non-numeric with 0
                                    total_not_enrolled = pd.to_numeric(branch_data['Not Enrolled Count'], errors='coerce').fillna(0).sum()
                                st.metric("Not Enrolled", f"{int(total_not_enrolled):,}")
                            
                            with col_d:
                                # Calculate total amount - need to clean currency values
                                total_amount = 0
                                if 'Total Enrolled Amount' in branch_data.columns:
                                    for val in branch_data['Total Enrolled Amount']:
                                        if val != '-' and pd.notna(val):
                                            try:
                                                # Remove ₹ symbol and commas, then convert to float
                                                clean_val = str(val).replace('₹', '').replace(',', '').strip()
                                                if clean_val and clean_val != '-':
                                                    total_amount += float(clean_val)
                                            except (ValueError, TypeError):
                                                # If conversion fails, try to extract just the number
                                                try:
                                                    import re
                                                    numbers = re.findall(r'[\d,]+', str(val))
                                                    if numbers:
                                                        clean_val = numbers[0].replace(',', '')
                                                        total_amount += float(clean_val)
                                                except:
                                                    pass
                                st.metric("Total Amount", f"₹{total_amount:,.0f}")
                            
                            # SINGLE DOWNLOAD BUTTON FOR BOTH REPORTS
                            st.markdown("---")
                            st.markdown("#### 💾 Download Both Reports Together")
                            
                            # Create Excel file with both reports
                            def create_branch_employee_excel(branch_df_data, employee_df_data):
                                excel_buffer = io.BytesIO()
                                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                                    # Write branch summary
                                    branch_df_data.to_excel(writer, sheet_name='Branch-wise Summary', index=False)
                                    
                                    # Write employee details
                                    employee_df_data.to_excel(writer, sheet_name='Employee-wise Details', index=False)
                                    
                                    # Add a summary sheet with filter info
                                    summary_data = {
                                        'Report Generated On': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
                                        'Date Filter Applied': [f"{filter_start_date} to {filter_end_date}" if filter_start_date and filter_end_date else "No Filter"],
                                        'Selected Branches': [', '.join(selected_branches)],
                                        'Total Schemes': [len(schemes)],
                                        'Schemes List': [', '.join(schemes)]
                                    }
                                    summary_df = pd.DataFrame(summary_data)
                                    summary_df.to_excel(writer, sheet_name='Report Info', index=False)
                                
                                return excel_buffer
                            
                            # Create the combined Excel file
                            combined_excel = create_branch_employee_excel(filtered_branch_df, filtered_employee_df)
                            
                            # Create filename with timestamp
                            timestamp_local = datetime.now().strftime('%Y%m%d_%H%M%S')
                            if filter_start_date and filter_end_date:
                                filename = f"branch_employee_referral_{filter_start_date}_to_{filter_end_date}_{timestamp_local}.xlsx"
                            else:
                                filename = f"branch_employee_referral_all_data_{timestamp_local}.xlsx"
                            
                            # Single download button
                            col1, col2, col3 = st.columns([1, 2, 1])
                            with col2:
                                st.download_button(
                                    label="📥 Download Both Reports (Excel)",
                                    data=combined_excel.getvalue(),
                                    file_name=filename,
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True,
                                    help="Download Branch-wise Summary and Employee-wise Details in a single Excel file"
                                )
                            
                            # Optional: Also provide individual CSV downloads if needed
                            with st.expander("📎 Additional Download Options"):
                                st.markdown("**Download individual reports as CSV:**")
                                
                                col_csv1, col_csv2 = st.columns(2)
                                with col_csv1:
                                    # Branch summary CSV
                                    csv_buffer_branch = io.StringIO()
                                    filtered_branch_df.to_csv(csv_buffer_branch, index=False)
                                    st.download_button(
                                        label="📥 Branch Summary (CSV)",
                                        data=csv_buffer_branch.getvalue(),
                                        file_name=f"branch_summary_{timestamp_local}.csv",
                                        mime="text/csv",
                                        use_container_width=True
                                    )
                                
                                with col_csv2:
                                    # Employee details CSV
                                    csv_buffer_employee = io.StringIO()
                                    filtered_employee_df.to_csv(csv_buffer_employee, index=False)
                                    st.download_button(
                                        label="📥 Employee Details (CSV)",
                                        data=csv_buffer_employee.getvalue(),
                                        file_name=f"employee_details_{timestamp_local}.csv",
                                        mime="text/csv",
                                        use_container_width=True
                                    )
                            
                        else:
                            st.info("ℹ️ No employee data available for the selected branches")
                else:
                    st.info("ℹ️ No data available for referral report")
            
            # Export all reports in one Excel file with date filter info
            st.markdown("---")
            st.markdown("### 💾 Export All Reports")
            
            col1, col2 = st.columns(2)
            
            with col1:
                excel_buffer = create_excel_report(
                    filtered_data,
                    generator,
                    filter_start_date,
                    filter_end_date
                )
                
                # Add filter info to filename if applied
                if filter_start_date and filter_end_date:
                    filename = f"complete_reports_{filter_start_date}_to_{filter_end_date}_{timestamp}.xlsx"
                else:
                    filename = f"complete_reports_all_data_{timestamp}.xlsx"
                
                st.download_button(
                    label="📥 Download All Reports (Excel - Complete)",
                    data=excel_buffer.getvalue(),
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            with col2:
                if filter_start_date and filter_end_date:
                    st.info(f"💡 **Filter Applied:** {filter_start_date} to {filter_end_date}\n\nThe Excel file will include filtered data only.")
                else:
                    st.info("💡 **Tip:** Use the date filters above to generate reports for specific time periods.\n\nYou can filter by week, month, or custom date range.")
            
        except Exception as e:
            st.markdown(f'<div class="error-box">❌ Error: {str(e)}</div>', unsafe_allow_html=True)
            st.info("💡 **Tip:** Please check that your files have the correct column names and data formats.")
    
    else:
        st.markdown("""
        <div class="info-box">
            👈 <strong>Getting Started</strong><br>
            Please upload all three required files (Employees, Referrals, and Transactions reports) to generate the consolidated report.
            The BSS Report is optional but recommended for better matching accuracy.
        </div>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
