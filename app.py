from pathlib import Path
from io import BytesIO
from html import escape
import json
import hashlib
import secrets
import time

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

# =========================================================
# CONFIGURATION
# =========================================================
st.set_page_config(
    page_title="Lendi CSE Result Analysis",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

BASE_DIR = Path(__file__).parent
FILE_PATH = BASE_DIR / "CSE_Demo_Grade_Points_With_Sections.xlsx"
ACCOUNTS_PATH = BASE_DIR / "users.json"
LOGO_PATH = BASE_DIR / "lendi_logo.png"  # Optional official logo image
SUBJECTS = ["Python", "DBMS", "DLCO", "MFCS", "UHV"]
FACULTY_ID = "python"
FACULTY_PASSWORD = "cse@faculty"
PBKDF2_ITERATIONS = 260_000
NAVY = "#052C65"
RED = "#E82A28"
PALE_RED = "#F1AEB5"

# =========================================================
# LENDI-INSPIRED THEME + CIRCULAR LOADER
# =========================================================
st.markdown(f"""
<style>
:root {{ --lendi-blue:{NAVY}; --lendi-red:{RED}; }}
.stApp {{ background:#F5F7FB; }}
[data-testid="stHeader"] {{ background:rgba(255,255,255,0.92); }}
h1,h2,h3 {{ color:{NAVY}; }}
[data-testid="stMetric"] {{ background:#FFFFFF; border:1px solid #E3EAF3;
  padding:16px; border-radius:14px; box-shadow:0 3px 12px rgba(5,44,101,.06); }}
[data-testid="stSidebar"] {{ background:{NAVY}; }}
[data-testid="stSidebar"] * {{ color:#FFFFFF !important; }}
[data-testid="stSidebar"] [data-testid="stRadio"] label {{ padding:7px 10px; border-radius:8px; }}
.stButton > button {{ background:{NAVY}; color:white; border:0; border-radius:9px; font-weight:600; }}
.stButton > button:hover {{ background:{RED}; color:white; border:0; }}
.stDownloadButton > button {{ border-radius:9px; border:1px solid {NAVY}; color:{NAVY}; }}
.lendi-banner {{ background:linear-gradient(110deg,{NAVY},#0B438C); color:white;
  padding:22px 26px; border-radius:16px; margin-bottom:18px; }}
.lendi-banner h1 {{ color:white !important; margin:0; }}
.lendi-muted {{ color:#64748B; font-size:13px; }}
.loader-wrap {{ min-height:75vh; display:flex; flex-direction:column; align-items:center;
  justify-content:center; text-align:center; color:{NAVY}; }}
.loader-ring {{ width:112px; height:112px; border-radius:50%; border:8px solid #DCE7F5;
  border-top:8px solid {RED}; border-right:8px solid {NAVY}; animation:lendi-spin 1s linear infinite;
  display:flex; align-items:center; justify-content:center; margin:18px auto; }}
.loader-inner {{ width:76px; height:76px; border-radius:50%; background:white; display:flex;
  align-items:center; justify-content:center; color:{NAVY}; font-size:30px; font-weight:800; }}
@keyframes lendi-spin {{ from {{ transform:rotate(0deg); }} to {{ transform:rotate(360deg); }} }}
@keyframes lendi-fade {{ from {{opacity:0; transform:translateY(8px);}} to {{opacity:1; transform:translateY(0);}} }}
.fade-in {{ animation:lendi-fade .7s ease-out; }}
</style>
""", unsafe_allow_html=True)

# =========================================================
# OPTIONAL INTRO ANIMATION (ONCE PER SESSION)
# =========================================================
if not st.session_state.get("intro_done", False):
    logo_html = "<div class='loader-inner'>L</div>"
    st.markdown("<div class='loader-wrap'>", unsafe_allow_html=True)
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=115)
    else:
        st.markdown(
            f"<div class='loader-ring'>{logo_html}</div>",
            unsafe_allow_html=True
        )
    st.markdown(
        f"<h2 style='color:{NAVY};margin-bottom:2px;'>LENDI INSTITUTE OF ENGINEERING & TECHNOLOGY</h2>"
        "<div style='font-weight:700;letter-spacing:1px;'>CSE RESULT ANALYSIS DASHBOARD</div>"
        f"<div style='color:{RED};margin-top:14px;'>Loading your dashboard...</div></div>",
        unsafe_allow_html=True
    )
    time.sleep(1.8)
    st.session_state.intro_done = True
    st.rerun()

# =========================================================
# DATA LOADING
# =========================================================
@st.cache_data
def load_data():
    if not FILE_PATH.exists():
        return None
    data = pd.read_excel(FILE_PATH)
    required = ["Student_ID", "Student_Name", "Section", "SGPA", "Result"] + SUBJECTS
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError("Missing Excel columns: " + ", ".join(missing))
    for subject in SUBJECTS:
        data[subject] = pd.to_numeric(data[subject], errors="coerce")
    data["SGPA"] = pd.to_numeric(data["SGPA"], errors="coerce")
    for column in ["Student_ID", "Student_Name", "Section"]:
        data[column] = data[column].astype(str).str.strip()
    return data

try:
    df = load_data()
except Exception as error:
    st.error(f"Unable to load Excel file: {error}")
    st.stop()

if df is None:
    st.error("Excel file not found. Keep CSE_Demo_Grade_Points_With_Sections.xlsx beside app.py.")
    st.stop()

# =========================================================
# STUDENT ACCOUNT MANAGEMENT (SALTED PBKDF2 HASHES)
# =========================================================
def load_accounts():
    if not ACCOUNTS_PATH.exists():
        return {}
    try:
        with ACCOUNTS_PATH.open("r", encoding="utf-8") as file:
            saved = json.load(file)
        return saved if isinstance(saved, dict) else {}
    except (json.JSONDecodeError, OSError):
        st.error("users.json could not be read. Check that the file is valid JSON.")
        st.stop()


def save_accounts(accounts):
    temporary = ACCOUNTS_PATH.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(accounts, file, indent=4)
    temporary.replace(ACCOUNTS_PATH)


def make_password_record(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return {"salt": salt, "password_hash": digest}


def verify_student_password(password, record):
    try:
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(record["salt"]), PBKDF2_ITERATIONS
        ).hex()
        return secrets.compare_digest(digest, record["password_hash"])
    except (KeyError, ValueError, TypeError):
        return False


def set_student_password(student_id, password):
    accounts = load_accounts()
    accounts[student_id] = make_password_record(password)
    save_accounts(accounts)

# =========================================================
# PDF REPORT GENERATOR
# =========================================================
def create_pdf(title, subtitle, table_data):
    buffer = BytesIO()
    page_size = landscape(A4) if len(table_data[0]) > 5 else A4
    doc = SimpleDocTemplate(buffer, pagesize=page_size,
                            rightMargin=35, leftMargin=35, topMargin=40, bottomMargin=35)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "LendiTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=19,
        textColor=colors.HexColor(NAVY), alignment=TA_CENTER, spaceAfter=10
    )
    subtitle_style = ParagraphStyle(
        "LendiSubtitle", parent=styles["Normal"], fontSize=9,
        textColor=colors.HexColor("#64748B"), alignment=TA_CENTER, spaceAfter=18
    )
    cell_style = ParagraphStyle(
        "LendiCell", parent=styles["Normal"], fontSize=8, leading=11,
        textColor=colors.HexColor("#334155")
    )
    header_style = ParagraphStyle(
        "LendiHeader", parent=cell_style, fontName="Helvetica-Bold",
        textColor=colors.white, alignment=TA_CENTER
    )
    content = [Paragraph(escape(str(title)), title_style),
               Paragraph(escape(str(subtitle)), subtitle_style), Spacer(1, 10)]
    safe_rows = []
    for row_index, row in enumerate(table_data):
        style = header_style if row_index == 0 else cell_style
        safe_rows.append([Paragraph(escape(str(value)), style) for value in row])
    table = Table(safe_rows, repeatRows=1, hAlign="CENTER")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    content.append(table)
    doc.build(content)
    return buffer.getvalue()

# =========================================================
# SESSION STATE + COMMON UI
# =========================================================
for key, default in [("logged_in", False), ("role", None), ("student_id", None)]:
    if key not in st.session_state:
        st.session_state[key] = default


def show_brand_header(title, subtitle):
    left, right = st.columns([1, 8])
    with left:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=78)
        else:
            st.markdown(
                f"<div style='background:{NAVY};color:white;border-radius:50%;width:64px;height:64px;"
                "display:flex;align-items:center;justify-content:center;font-size:30px;font-weight:800;'>L</div>",
                unsafe_allow_html=True
            )
    with right:
        st.markdown(
            f"<div class='fade-in'><div style='font-size:12px;color:{RED};font-weight:700;letter-spacing:1px;'>"
            "LENDI INSTITUTE OF ENGINEERING & TECHNOLOGY</div>"
            f"<h1 style='margin:0;color:{NAVY};'>{title}</h1>"
            f"<div class='lendi-muted'>{subtitle}</div></div>",
            unsafe_allow_html=True
        )


def logout():
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.student_id = None
    st.rerun()

# =========================================================
# LOGIN PAGE
# =========================================================
def login_page():
    show_brand_header("CSE RESULT ANALYSIS", "Student Academic Performance Management System")
    st.divider()
    _, center, _ = st.columns([1, 1.25, 1])
    with center:
        st.markdown(f"<div class='lendi-banner'><h1>Welcome</h1><div>Secure Academic Portal</div></div>", unsafe_allow_html=True)
        role = st.selectbox("Select Login Type", ["Faculty", "Student"])
        user_id = st.text_input("User ID", placeholder="Enter your ID")
        password = st.text_input("Password", type="password")
        if st.button("Login", use_container_width=True):
            if role == "Faculty":
                if user_id.strip() == FACULTY_ID and password == FACULTY_PASSWORD:
                    st.session_state.logged_in = True
                    st.session_state.role = "Faculty"
                    st.rerun()
                else:
                    st.error("Invalid Faculty ID or Password.")
            else:
                sid = user_id.strip()
                record = df[df["Student_ID"] == sid]
                accounts = load_accounts()
                if record.empty:
                    st.error("Student ID not found in the dataset.")
                elif sid in accounts and verify_student_password(password, accounts[sid]):
                    st.session_state.logged_in = True
                    st.session_state.role = "Student"
                    st.session_state.student_id = sid
                    st.rerun()
                elif sid not in accounts and password == sid:
                    # Default student credentials: User ID = Roll Number,
                    # Password = Roll Number. Store a salted hash on first login.
                    set_student_password(sid, sid)
                    st.session_state.logged_in = True
                    st.session_state.role = "Student"
                    st.session_state.student_id = sid
                    st.rerun()
                else:
                    st.error("Invalid Student ID or Password. Use your roll number as the default password if this is your first login.")
        st.caption("First-time student login: use your roll number as both User ID and password. Change your password after logging in.")

# =========================================================
# FACULTY: ACCOUNT MANAGEMENT
# =========================================================
def faculty_accounts_page():
    st.subheader("🔐 Student Account Management")
    st.write("Create a login account or reset a student's password. Passwords are stored as salted PBKDF2 hashes.")
    options = df[["Student_ID", "Student_Name"]].drop_duplicates().copy()
    options["display"] = options["Student_ID"] + " — " + options["Student_Name"]
    choice = st.selectbox("Select Student", options["display"].tolist())
    sid = options.loc[options["display"] == choice, "Student_ID"].iloc[0]
    new_password = st.text_input("Set temporary / new password", type="password", key="faculty_new_pw")
    confirm = st.text_input("Confirm password", type="password", key="faculty_confirm_pw")
    if st.button("Create / Reset Student Account"):
        if len(new_password) < 8:
            st.error("Password must contain at least 8 characters.")
        elif new_password != confirm:
            st.error("Passwords do not match.")
        else:
            set_student_password(sid, new_password)
            st.success(f"Account saved for {sid}. Share the password securely with the student.")
    accounts = load_accounts()
    st.metric("Accounts Created", f"{len(accounts)} / {df['Student_ID'].nunique()}")

# =========================================================
# FACULTY: OVERVIEW / ANALYTICS
# =========================================================
def faculty_overview():
    st.subheader("📊 Academic Overview")
    sections = ["All Sections"] + sorted(df["Section"].dropna().unique().tolist())
    section = st.selectbox("Filter by Section", sections, key="faculty_section_filter")
    data = df.copy() if section == "All Sections" else df[df["Section"] == section].copy()
    total = len(data)
    avg = data["SGPA"].mean()
    high = data["SGPA"].max()
    low = data["SGPA"].min()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Students", total)
    c2.metric("Average SGPA", f"{avg:.2f}" if pd.notna(avg) else "N/A")
    c3.metric("Highest SGPA", f"{high:.2f}" if pd.notna(high) else "N/A")
    c4.metric("Lowest SGPA", f"{low:.2f}" if pd.notna(low) else "N/A")
    passed = (data["Result"].astype(str).str.upper() == "PASS").sum()
    failed = (data["Result"].astype(str).str.upper() == "FAIL").sum()
    a, b, c = st.columns(3)
    a.metric("Passed", int(passed))
    b.metric("Failed", int(failed))
    c.metric("Incomplete / Other", int(total - passed - failed))
    st.divider()
    left, right = st.columns(2)
    with left:
        st.markdown("#### Subject-wise Average Grade Points")
        fig, ax = plt.subplots(figsize=(7, 4))
        data[SUBJECTS].mean().plot(kind="bar", ax=ax, color=NAVY)
        ax.set_ylim(0, 10)
        ax.set_ylabel("Average Grade Point")
        ax.tick_params(axis="x", rotation=0)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
    with right:
        st.markdown("#### SGPA Distribution")
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(data["SGPA"].dropna(), bins=10, color=RED, edgecolor="white")
        ax.set_xlabel("SGPA")
        ax.set_ylabel("Students")
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
    st.markdown("#### 🏆 Top 10 Students")
    top = data.sort_values("SGPA", ascending=False).head(10)
    st.dataframe(top[["Student_ID", "Student_Name", "Section", "SGPA", "Result"]], use_container_width=True, hide_index=True)


def faculty_records_page():
    st.subheader("📋 Student Records")
    search = st.text_input("Search by Student ID or Name")
    data = df.copy()
    if search:
        mask = (data["Student_ID"].str.contains(search, case=False, na=False) |
                data["Student_Name"].str.contains(search, case=False, na=False))
        data = data[mask]
    st.dataframe(data, use_container_width=True, hide_index=True)
    st.download_button("📥 Download CSV", data=data.to_csv(index=False).encode("utf-8"),
                       file_name="CSE_Result_Report.csv", mime="text/csv")


def faculty_sections_page():
    st.subheader("🏫 Section-wise Analysis")
    section_order = sorted(df["Section"].dropna().astype(str).unique().tolist())

    # Section performance summary and ranking
    summary = (
        df.groupby("Section", dropna=True)
        .agg(
            Total_Students=("Student_ID", "count"),
            Average_SGPA=("SGPA", "mean"),
            Highest_SGPA=("SGPA", "max"),
            Lowest_SGPA=("SGPA", "min"),
        )
        .reset_index()
    )
    summary[["Average_SGPA", "Highest_SGPA", "Lowest_SGPA"]] = (
        summary[["Average_SGPA", "Highest_SGPA", "Lowest_SGPA"]].round(2)
    )
    ranked = summary.sort_values(
        ["Average_SGPA", "Highest_SGPA"], ascending=[False, False]
    ).reset_index(drop=True)
    ranked.insert(0, "Rank", range(1, len(ranked) + 1))

    st.markdown("### 🥇 Section Performance Ranking")
    st.dataframe(ranked, use_container_width=True, hide_index=True)

    if not ranked.empty:
        best = ranked.iloc[0]
        st.success(
            f"Best-performing section: {best['Section']} "
            f"— Average SGPA {best['Average_SGPA']:.2f}"
        )

    # Average SGPA chart
    st.markdown("### 📊 Section-wise Average SGPA")
    chart_data = summary.sort_values("Section").set_index("Section")[["Average_SGPA"]]
    st.bar_chart(chart_data, y="Average_SGPA", height=320)

    # Subject comparison table and chart
    st.markdown("### 📚 Subject-wise Section Comparison")
    subject_summary = (
        df.groupby("Section")[SUBJECTS]
        .mean()
        .reindex(section_order)
        .round(2)
    )
    st.dataframe(subject_summary, use_container_width=True)
    st.bar_chart(subject_summary, height=360)

    # Overall class topper (include ties)
    st.markdown("### 🏆 Overall Class Topper")
    valid_sgpa = df["SGPA"].dropna()
    if valid_sgpa.empty:
        st.info("No valid SGPA values are available.")
    else:
        highest_sgpa = valid_sgpa.max()
        toppers = df[df["SGPA"] == highest_sgpa].sort_values(
            ["Student_Name", "Student_ID"]
        )
        st.metric("Highest SGPA", f"{highest_sgpa:.2f}")
        st.dataframe(
            toppers[["Student_ID", "Student_Name", "Section", "SGPA", "Result"]],
            use_container_width=True,
            hide_index=True,
        )

    # Top five students for every section
    st.markdown("### ⭐ Top 5 Students in Each Section")
    for sec in section_order:
        section_data = df[df["Section"].astype(str) == sec].copy()
        top_five = section_data.sort_values(
            ["SGPA", "Student_Name"], ascending=[False, True], na_position="last"
        ).head(5)
        with st.expander(f"Section {sec} — Top 5 Students", expanded=False):
            st.dataframe(
                top_five[["Student_ID", "Student_Name", "SGPA", "Result"]],
                use_container_width=True,
                hide_index=True,
            )


def faculty_reports_page():
    st.subheader("📄 Faculty Reports")
    sections = ["All Sections"] + sorted(df["Section"].dropna().unique().tolist())
    section = st.selectbox("Report section", sections, key="pdf_section")
    data = df.copy() if section == "All Sections" else df[df["Section"] == section].copy()
    avg = data["SGPA"].mean()
    top = data.sort_values("SGPA", ascending=False).head(10)
    report_rows = [["Student ID", "Name", "Section", "SGPA", "Result"]]
    for _, row in top.iterrows():
        report_rows.append([row["Student_ID"], row["Student_Name"], row["Section"],
                            f"{row['SGPA']:.2f}" if pd.notna(row["SGPA"]) else "N/A", row["Result"]])
    pdf = create_pdf("Lendi CSE Faculty Result Report",
                     f"Students: {len(data)} | Average SGPA: {avg:.2f} | Scope: {section}", report_rows)
    st.download_button("⬇️ Download Faculty PDF", data=pdf, file_name="Lendi_CSE_Faculty_Report.pdf",
                       mime="application/pdf")
    st.caption("PDF includes the top 10 students for the selected section.")

# =========================================================
# STUDENT PAGES
# =========================================================
def get_current_student():
    records = df[df["Student_ID"] == st.session_state.student_id]
    return None if records.empty else records.iloc[0]


def student_class_rank(student):
    valid = df["SGPA"].dropna()
    if pd.isna(student["SGPA"]) or valid.empty:
        return None
    # Competition ranking: students with the same SGPA receive the same rank.
    return int((valid > float(student["SGPA"])).sum() + 1)


def student_overview(student):
    st.subheader(f"Welcome, {student['Student_Name']}!")
    class_average = df["SGPA"].mean()
    rank = student_class_rank(student)
    total_students = int(df["SGPA"].notna().sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Student ID", student["Student_ID"])
    c2.metric("Section", student["Section"])
    c3.metric("Your SGPA", f"{student['SGPA']:.2f}" if pd.notna(student["SGPA"]) else "N/A")
    c4.metric("Overall Class Rank", f"{rank} / {total_students}" if rank is not None else "N/A")

    st.markdown("### 📈 SGPA Performance Summary")
    left, right = st.columns(2)
    with left:
        st.metric("Your SGPA", f"{student['SGPA']:.2f}" if pd.notna(student["SGPA"]) else "N/A")
    with right:
        st.metric("Class Average SGPA", f"{class_average:.2f}" if pd.notna(class_average) else "N/A")

    if pd.notna(student["SGPA"]) and pd.notna(class_average):
        difference = float(student["SGPA"]) - float(class_average)
        if difference > 0:
            st.success(f"You are {difference:.2f} SGPA points above the class average.")
        elif difference < 0:
            st.info(f"You are {abs(difference):.2f} SGPA points below the class average.")
        else:
            st.info("Your SGPA is equal to the class average.")

        comparison = pd.DataFrame({
            "Category": ["Your SGPA", "Class Average"],
            "SGPA": [float(student["SGPA"]), float(class_average)],
        }).set_index("Category")
        st.bar_chart(comparison, y="SGPA", height=230)

    st.markdown("### 📚 Subject-wise Performance")
    subject_data = pd.DataFrame({
        "Subject": SUBJECTS,
        "Your Grade Point": [student[s] for s in SUBJECTS],
        "Class Average": [df[s].mean() for s in SUBJECTS],
    })
    st.dataframe(subject_data.round(2), use_container_width=True, hide_index=True)
    chart_data = subject_data.set_index("Subject")
    st.bar_chart(chart_data, height=330)

    st.caption(
        "Class rank is calculated across all students with a valid SGPA. "
        "Students with equal SGPA receive the same rank. No section rank is displayed."
    )


def student_profile_page(student):
    st.subheader("👤 My Student Profile")
    rank = student_class_rank(student)
    total_students = int(df["SGPA"].notna().sum())
    profile_left, profile_right = st.columns([1, 2])
    with profile_left:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=125)
        st.markdown("#### Academic Profile")
        st.metric("Overall Class Rank", f"{rank} / {total_students}" if rank is not None else "N/A")
    with profile_right:
        profile = pd.DataFrame([
            ["Student Name", student["Student_Name"]],
            ["Student ID", student["Student_ID"]],
            ["Section", student["Section"]],
            ["SGPA", f"{student['SGPA']:.2f}" if pd.notna(student["SGPA"]) else "N/A"],
            ["Result", student["Result"]],
        ], columns=["Profile Field", "Details"])
        st.dataframe(profile, use_container_width=True, hide_index=True)

    st.markdown("#### Subject Grade Points")
    profile_subjects = pd.DataFrame({
        "Subject": SUBJECTS,
        "Grade Point": [student[s] for s in SUBJECTS],
    })
    st.dataframe(profile_subjects, use_container_width=True, hide_index=True)


def student_result_page(student):
    st.subheader("📄 My Result")
    rows = [["Subject", "Grade Point"]]
    for subject in SUBJECTS:
        value = student[subject]
        rows.append([subject, value if pd.notna(value) else "N/A"])
    rows.extend([["SGPA", f"{student['SGPA']:.2f}" if pd.notna(student["SGPA"]) else "N/A"],
                 ["Result", student["Result"]]])
    st.table(pd.DataFrame(rows[1:], columns=rows[0]))
    pdf = create_pdf("Lendi CSE Student Result", f"{student['Student_Name']} | {student['Student_ID']} | Section {student['Section']}", rows)
    st.download_button("⬇️ Download My Result PDF", data=pdf,
                       file_name=f"{student['Student_ID']}_Result.pdf", mime="application/pdf")


def student_password_page():
    st.subheader("🔑 Change My Password")
    current = st.text_input("Current password", type="password", key="stu_current")
    new = st.text_input("New password (minimum 8 characters)", type="password", key="stu_new")
    confirm = st.text_input("Confirm new password", type="password", key="stu_confirm")
    if st.button("Update Password"):
        account = load_accounts().get(st.session_state.student_id)
        if not account or not verify_student_password(current, account):
            st.error("Current password is incorrect.")
        elif len(new) < 8:
            st.error("New password must contain at least 8 characters.")
        elif new != confirm:
            st.error("New passwords do not match.")
        else:
            set_student_password(st.session_state.student_id, new)
            st.success("Password updated. Use the new password next time you log in.")

# =========================================================
# MAIN APP + SIDEBAR NAVIGATION
# =========================================================
if not st.session_state.logged_in:
    login_page()
else:
    if st.session_state.role == "Faculty":
        with st.sidebar:
            if LOGO_PATH.exists():
                st.image(str(LOGO_PATH), width=105)
            else:
                st.markdown("<h1 style='color:white;text-align:center;'>LENDI</h1>", unsafe_allow_html=True)
            st.markdown("### FACULTY PORTAL")
            st.caption("CSE Result Analysis")
            page = st.radio("NAVIGATION", ["Overview", "Student Accounts", "Student Records", "Section Analysis", "Reports"])
            st.divider()
            st.caption("Logged in as Faculty")
            if st.button("Logout", use_container_width=True):
                logout()
        show_brand_header("FACULTY DASHBOARD", "Academic performance and student result management")
        if page == "Overview":
            faculty_overview()
        elif page == "Student Accounts":
            faculty_accounts_page()
        elif page == "Student Records":
            faculty_records_page()
        elif page == "Section Analysis":
            faculty_sections_page()
        elif page == "Reports":
            faculty_reports_page()
    
    elif st.session_state.role == "Student":
        student = get_current_student()
        if student is None:
            st.error("Student record not found. Contact faculty.")
            st.stop()
        with st.sidebar:
            if LOGO_PATH.exists():
                st.image(str(LOGO_PATH), width=105)
            else:
                st.markdown("<h1 style='color:white;text-align:center;'>LENDI</h1>", unsafe_allow_html=True)
            st.markdown("### STUDENT PORTAL")
            st.caption(student["Student_Name"])
            page = st.radio("NAVIGATION", ["My Overview", "My Profile", "My Result", "Change Password"])
            st.divider()
            st.caption(f"Student ID: {st.session_state.student_id}")
            if st.button("Logout", use_container_width=True):
                logout()
        show_brand_header("STUDENT DASHBOARD", "Your personal academic performance portal")
        if page == "My Overview":
            student_overview(student)
        elif page == "My Profile":
            student_profile_page(student)
        elif page == "My Result":
            student_result_page(student)
        elif page == "Change Password":
            student_password_page()

# Footer
st.markdown("<hr><div style='text-align:center;color:#718096;font-size:12px;'>Lendi CSE Result Analysis Dashboard</div>", unsafe_allow_html=True)
