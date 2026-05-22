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
        
        # 16. Month (extract month name from Updated Date)
        final_report['Month'] = final_report['Updated Date'].apply(
            lambda x: x.strftime('%B').lower() if pd.notna(x) else ''
        )
        
        # Select final columns in the specified order
        final_columns = [
            'Updated Date', 'Customer Name', 'Customer Phone', 'Customer Enrollment Amount',
            'Status', 'Employee Name', 'Referral Code', 'Employee Phone', 'Employee Code',
            'Branch', 'Customer Payment', 'True/False', 'Scheme Name', 'Scheme Passbook Number',
            'Category', 'Month'
        ]
        
        # Ensure all columns exist
        for col in final_columns:
            if col not in final_report.columns:
                final_report[col] = np.nan
        
        # Show match statistics
        matched_count = final_report['Customer Payment'].notna().sum()
        if len(final_report) > 0:
            st.info(f"📊 Match Results: {matched_count} out of {len(final_report)} records matched with transactions ({matched_count/len(final_report)*100:.1f}%)")
        
        # Show category distribution
        category_counts = final_report['Category'].value_counts()
        st.info(f"📊 Category Distribution: {dict(category_counts)}")
        
        # Show branch distribution
        branch_counts = final_report['Branch'].value_counts().head(10)
        st.info(f"📊 Top 10 Branches: {dict(branch_counts)}")
        
        return final_report[final_columns]

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
    
    # Matching Logic Explanation
    with st.expander("🔍 Understanding the Logic"):
        st.markdown("""
        ### Updated Date Logic:
        
        The **Updated Date** is selected based on the **Status** field:
        
        - **If Status contains "Scheme Joined" or "joined"** → Uses **Joined Date**
        - **If Status contains "Customer Register" or "registered"** → Uses **Registered Date**
        - **For any other status** → Defaults to **Joined Date** (if available), otherwise **Registered Date**
        
        ### Branch Transformation Logic (with Proper Case):
        
        The **Branch** field is transformed using the following rules:
        
        1. If branch is empty → "Bhima Jewellery - Customer"
        2. If branch is "HEAD OFFICE" → "Bhima Jewellery - Madurai"
        3. If branch is "IN-TRANSIT- LOCATIONS" → "Bhima Jewellery - Salem"
        4. If branch is "APP SHOWROOM LOCATION" → "Bhima Jewellery - Tirunelveli"
        5. If branch already contains "Bhima Jewellery -" → Keep as is (with proper case)
        6. If branch ends with "BRANCH" → Remove "BRANCH" and add prefix (with proper case)
        7. Otherwise → Add "Bhima Jewellery - " prefix (with proper case)
        8. Finally, replace "Tiruchirappalli" with "Trichy" and ensure proper case
        
        **Proper Case Examples:**
        - "salem branch" → "Bhima Jewellery - Salem"
        - "chennai" → "Bhima Jewellery - Chennai"
        - "TIRUNELVELI" → "Bhima Jewellery - Tirunelveli"
        
        ### How Customer Payment, Scheme Name, and Passbook Number are matched:
        
        The system looks for a transaction that matches **ALL THREE conditions**:
        
        1. **Customer Phone Number** matches between Referrals and Transactions
        2. **Paid Date** matches the Updated Date (selected based on Status)
        3. **Installment number** must be exactly 1 (first installment)
        
        ### Category Field Logic:
        
        - **Category** is taken from `Employee Type` in the Employees Report based on matching `Referral Code`
        - If no match is found or the value is blank, it defaults to **"Customer"**
        """)
    
    # Column requirements help
    with st.expander("📋 View Required Column Names"):
        col_req1, col_req2, col_req3 = st.columns(3)
        
        with col_req1:
            st.markdown("**Employees Report**")
            st.markdown("""
            - `Referral Code`\n
            - `Employee Code`\n
            - `Branch` (Will be transformed to proper case)\n
            - `Employee Type` (Optional - defaults to "Customer")
            """)
        
        with col_req2:
            st.markdown("**Referrals Report**")
            st.markdown("""
            - `Status`\n
            - `Joined Date` (Used for "Scheme Joined" status)\n
            - `Registered Date` (Used for "Customer Register" status)\n
            - `Referee Name`\n
            - `Referee Phone`\n
            - `Enrollment Amount`\n
            - `Referrer Name`\n
            - `Referral Code`\n
            - `Referrer Phone`
            """)
        
        with col_req3:
            st.markdown("**Transactions Report**")
            st.markdown("""
            - `Customer Phone Number`\n
            - `Saved Amount`\n
            - `Installment number` (must be 1 for matching)\n
            - `Paid Date`\n
            - `Scheme Name`\n
            - `Passbook number`
            """)
    
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
            
            # Validate other required columns
            required_emp = ['Referral Code', 'Employee Code', 'Branch']
            required_ref = ['Referee Name', 'Referee Phone', 'Enrollment Amount', 
                           'Status', 'Referrer Name', 'Referral Code', 'Referrer Phone']
            required_trans = ['Customer Phone Number', 'Saved Amount', 'Installment number', 'Paid Date']
            
            missing_cols = []
            
            for col in required_emp:
                if col not in employees_df.columns:
                    missing_cols.append(f"Employees: {col}")
            
            for col in required_ref:
                if col not in referrals_df.columns:
                    missing_cols.append(f"Referrals: {col}")
            
            for col in required_trans:
                if col not in transactions_df.columns:
                    missing_cols.append(f"Transactions: {col}")
            
            if missing_cols:
                st.markdown('<div class="warning-box">⚠️ Missing Required Columns:</div>', unsafe_allow_html=True)
                for col in missing_cols:
                    st.write(f"- {col}")
                st.stop()
            
            # Check if Employee Type exists, if not, add default
            if 'Employee Type' not in employees_df.columns:
                st.warning("⚠️ 'Employee Type' column not found in Employees Report. All categories will be set to 'Customer'")
                employees_df['Employee Type'] = 'Customer'
            
            # Display data preview
            with st.expander("📊 View Uploaded Data Preview"):
                tab1, tab2, tab3 = st.tabs(["Employees Data", "Referrals Data", "Transactions Data"])
                with tab1:
                    st.dataframe(employees_df.head(10), use_container_width=True)
                    st.caption(f"Total Records: {len(employees_df)}")
                    
                    # Show unique branch values before transformation
                    if 'Branch' in employees_df.columns:
                        st.write("Sample original branch names:")
                        st.dataframe(employees_df['Branch'].dropna().unique()[:10])
                with tab2:
                    st.dataframe(referrals_df.head(10), use_container_width=True)
                    st.caption(f"Total Records: {len(referrals_df)}")
                    # Show status distribution
                    if 'Status' in referrals_df.columns:
                        st.write("Status Distribution:")
                        st.dataframe(referrals_df['Status'].value_counts())
                with tab3:
                    st.dataframe(transactions_df.head(10), use_container_width=True)
                    st.caption(f"Total Records: {len(transactions_df)}")
            
            # Generate report
            with st.spinner("Generating consolidated report..."):
                generator = ReportGenerator(employees_df, referrals_df, transactions_df)
                final_report = generator.generate_report()
                
                if final_report is None:
                    st.error("Failed to generate report. Please check your data.")
                    st.stop()
            
            # Display success message
            st.markdown('<div class="success-box">✅ Report generated successfully!</div>', unsafe_allow_html=True)
            
            # Display final report
            st.subheader("📈 Final Consolidated Report")
            st.dataframe(final_report, use_container_width=True, height=400)
            
            # Statistics
            st.subheader("📊 Report Statistics")
            col1, col2, col3, col4, col5 = st.columns(5)
            
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
            
            # Show sample of matched vs unmatched
            st.subheader("📋 Sample Records")
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**✅ Matched Records (First 5)**")
                matched_records = final_report[final_report['Customer Payment'].notna()].head(5)
                if len(matched_records) > 0:
                    st.dataframe(matched_records[['Customer Name', 'Customer Phone', 'Updated Date', 'Status', 'Customer Enrollment Amount', 'Customer Payment', 'Branch']])
                else:
                    st.info("No matched records found")
            
            with col2:
                st.markdown("**❌ Unmatched Records (First 5)**")
                unmatched_records = final_report[final_report['Customer Payment'].isna()].head(5)
                if len(unmatched_records) > 0:
                    st.dataframe(unmatched_records[['Customer Name', 'Customer Phone', 'Updated Date', 'Status', 'Customer Enrollment Amount', 'Branch']])
                else:
                    st.info("No unmatched records found")
            
            # Category distribution
            if 'Category' in final_report.columns:
                st.subheader("📊 Category Distribution")
                category_dist = final_report['Category'].value_counts()
                st.bar_chart(category_dist)
                
                # Show category details
                st.write("Category Breakdown:")
                for category, count in category_dist.items():
                    st.write(f"- **{category}**: {count} records ({count/len(final_report)*100:.1f}%)")
            
            # Branch distribution
            st.subheader("🏢 Branch Distribution (Top 10)")
            branch_dist = final_report['Branch'].value_counts().head(10)
            st.bar_chart(branch_dist)
            st.write("Top Branches:")
            for branch, count in branch_dist.items():
                st.write(f"- **{branch}**: {count} records ({count/len(final_report)*100:.1f}%)")
            
            # Monthly summary
            st.subheader("📅 Monthly Summary")
            monthly_summary = final_report.groupby('Month').agg({
                'Customer Name': 'count',
                'Customer Enrollment Amount': 'sum',
                'True/False': 'sum'
            }).rename(columns={
                'Customer Name': 'Number of Customers',
                'Customer Enrollment Amount': 'Total Amount',
                'True/False': 'Matched Payments'
            })
            st.dataframe(monthly_summary, use_container_width=True)
            
            # Export options
            st.subheader("💾 Export Report")
            
            col1, col2, col3 = st.columns(3)
            
            # Get current timestamp for filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            with col1:
                # Export to CSV
                csv_buffer = io.StringIO()
                final_report.to_csv(csv_buffer, index=False)
                st.download_button(
                    label="📥 Download as CSV",
                    data=csv_buffer.getvalue(),
                    file_name=f"consolidated_report_{timestamp}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with col2:
                # Export to Excel
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    final_report.to_excel(writer, sheet_name='Consolidated Report', index=False)
                    
                    # Add unmatched records sheet
                    unmatched = final_report[final_report['Customer Payment'].isna()]
                    if len(unmatched) > 0:
                        unmatched.to_excel(writer, sheet_name='Unmatched Records', index=False)
                    
                    # Add summary sheet
                    if not monthly_summary.empty:
                        monthly_summary.to_excel(writer, sheet_name='Monthly Summary')
                    
                    # Add category distribution
                    if 'Category' in final_report.columns:
                        category_df = final_report['Category'].value_counts().reset_index()
                        category_df.columns = ['Category', 'Count']
                        category_df.to_excel(writer, sheet_name='Category Distribution', index=False)
                    
                    # Add branch distribution
                    branch_df = final_report['Branch'].value_counts().reset_index()
                    branch_df.columns = ['Branch', 'Count']
                    branch_df.to_excel(writer, sheet_name='Branch Distribution', index=False)
                    
                    # Add date selection summary
                    if 'Status' in referrals_df.columns:
                        status_summary = referrals_df.groupby('Status').size().reset_index()
                        status_summary.columns = ['Status', 'Count']
                        status_summary.to_excel(writer, sheet_name='Status Summary', index=False)
                    
                    # Add statistics sheet
                    stats_data = {
                        'Metric': ['Total Records', 'Total Enrollment Amount', 'Total Payments', 'Matched Records', 'Match Rate'],
                        'Value': [
                            len(final_report),
                            f"₹{final_report['Customer Enrollment Amount'].sum():,.2f}",
                            f"₹{final_report['Customer Payment'].sum():,.2f}",
                            int(matched),
                            f"{match_percent:.1f}%"
                        ]
                    }
                    stats_df = pd.DataFrame(stats_data)
                    stats_df.to_excel(writer, sheet_name='Statistics', index=False)
                
                st.download_button(
                    label="📥 Download as Excel",
                    data=excel_buffer.getvalue(),
                    file_name=f"consolidated_report_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            with col3:
                # Download as JSON
                json_buffer = io.StringIO()
                final_report.to_json(json_buffer, orient='records', date_format='iso')
                st.download_button(
                    label="📥 Download as JSON",
                    data=json_buffer.getvalue(),
                    file_name=f"consolidated_report_{timestamp}.json",
                    mime="application/json",
                    use_container_width=True
                )
            
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            st.info("Please check that your files have the correct column names and data formats.")
    
    else:
        st.info("👈 **Please upload all three files** (Employees, Referrals, and Transactions reports) to generate the consolidated report.")

if __name__ == "__main__":
    main()