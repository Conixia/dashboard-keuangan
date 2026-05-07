import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests as req
from datetime import datetime
from fpdf import FPDF
import io

# ══════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Dashboard Keuangan",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp { background-color: #0f1117; }
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #1e2130, #252b3d);
        border: 1px solid #2d3250;
        border-radius: 12px;
        padding: 16px !important;
    }
    [data-testid="stMetricValue"] { color: #f0f4ff; font-size: 1.4rem !important; }
    [data-testid="stMetricLabel"] { color: #8892b0; }
    [data-testid="stSidebar"] { background-color: #141622; border-right: 1px solid #1e2130; }
    h1, h2, h3 { color: #e0e8ff !important; }
    .stDownloadButton button {
        background: linear-gradient(90deg, #4f46e5, #7c3aed);
        color: white; border: none;
        border-radius: 8px; font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
#  CEK QUERY PARAM
# ══════════════════════════════════════════════════════════
params       = st.query_params
current_user = params.get("user", "").strip()

if not current_user:
    st.markdown("## 💰 Dashboard Keuangan")
    st.info("Link dashboard tidak valid. Dapatkan link dashboard kamu lewat bot Telegram dengan perintah /dashboard")
    st.stop()

# ══════════════════════════════════════════════════════════
#  SUPABASE
# ══════════════════════════════════════════════════════════
def get_headers():
    key = st.secrets["SUPABASE_KEY"]
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json"
    }

@st.cache_data(ttl=60)
def load_data(username: str) -> pd.DataFrame:
    url  = st.secrets["SUPABASE_URL"]
    hdrs = get_headers()
    try:
        r = req.get(
            f"{url}/rest/v1/transactions?order=date.asc&select=*&username=eq.{username}",
            headers=hdrs, timeout=15
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        st.error(f"Gagal mengambil data: {e}")
        return pd.DataFrame()

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df["date"]        = pd.to_datetime(df["date"])
    df["amount"]      = df["amount"].astype(float)
    df["bulan"]       = df["date"].dt.to_period("M").astype(str)
    df["bulan_label"] = df["date"].dt.strftime("%b %Y")
    return df

def fmt_rp(n: float) -> str:
    return f"Rp {n:,.0f}".replace(",", ".")

# ══════════════════════════════════════════════════════════
#  PDF GENERATOR
# ══════════════════════════════════════════════════════════
def generate_pdf(df, username, periode, total_inc, total_exp, saldo) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(30, 30, 60)
    pdf.cell(0, 12, "Laporan Keuangan Pribadi", ln=True, align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 100, 120)
    pdf.cell(0, 7, f"Pengguna: {username}  |  Periode: {periode}", ln=True, align="C")
    pdf.cell(0, 7, f"Digenerate: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align="C")
    pdf.ln(6)

    pdf.set_draw_color(200, 200, 220)
    pdf.set_line_width(0.5)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(30, 30, 60)
    pdf.cell(0, 8, "Ringkasan", ln=True)
    pdf.ln(2)

    def summary_row(label, value, color=(30, 30, 60)):
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(100, 100, 120)
        pdf.cell(70, 8, label)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*color)
        pdf.cell(0, 8, value, ln=True)

    summary_row("Total Pemasukan :", fmt_rp(total_inc), (34, 139, 34))
    summary_row("Total Pengeluaran:", fmt_rp(total_exp), (180, 30, 30))
    summary_row("Saldo            :", fmt_rp(saldo),
                (34, 139, 34) if saldo >= 0 else (180, 30, 30))
    summary_row("Jumlah Transaksi :", str(len(df)))
    pdf.ln(6)

    exp_df = df[df["type"] == "pengeluaran"]
    if not exp_df.empty:
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(30, 30, 60)
        pdf.cell(0, 8, "Pengeluaran per Kategori", ln=True)
        pdf.ln(2)
        by_cat = exp_df.groupby("category")["amount"].sum().sort_values(ascending=False)
        for cat, amt in by_cat.items():
            pct = amt / total_exp * 100 if total_exp else 0
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(80, 80, 100)
            pdf.cell(80, 7, f"  {cat}")
            pdf.set_text_color(30, 30, 60)
            pdf.cell(60, 7, fmt_rp(amt))
            pdf.set_text_color(130, 130, 150)
            pdf.cell(0, 7, f"{pct:.1f}%", ln=True)
        pdf.ln(6)

    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(30, 30, 60)
    pdf.cell(0, 8, "Rincian Transaksi", ln=True)
    pdf.ln(2)

    pdf.set_fill_color(230, 230, 245)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(50, 50, 80)
    pdf.cell(25, 7, "Tanggal",    border=1, fill=True)
    pdf.cell(30, 7, "Jenis",      border=1, fill=True)
    pdf.cell(35, 7, "Kategori",   border=1, fill=True)
    pdf.cell(45, 7, "Jumlah",     border=1, fill=True)
    pdf.cell(0,  7, "Keterangan", border=1, fill=True, ln=True)

    pdf.set_font("Helvetica", "", 8)
    for _, row in df.iterrows():
        if pdf.get_y() > 270:
            pdf.add_page()
        color = (34, 100, 34) if row["type"] == "pemasukan" else (150, 30, 30)
        pdf.set_text_color(60, 60, 80)
        pdf.cell(25, 6, row["date"].strftime("%d/%m/%Y"), border=1)
        pdf.set_text_color(*color)
        pdf.cell(30, 6, row["type"].title(), border=1)
        pdf.set_text_color(60, 60, 80)
        pdf.cell(35, 6, str(row["category"]), border=1)
        pdf.cell(45, 6, fmt_rp(row["amount"]), border=1)
        pdf.cell(0,  6, str(row["description"])[:28], border=1, ln=True)

    return bytes(pdf.output())

# ══════════════════════════════════════════════════════════
#  LOAD DATA
# ══════════════════════════════════════════════════════════
df_raw = load_data(current_user)

# ══════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(f"### 👤 {current_user}")
    st.markdown("---")
    st.markdown("## 🔍 Filter")

    if not df_raw.empty:
        bulan_opts = ["Semua"] + sorted(df_raw["bulan"].unique().tolist(), reverse=True)
        sel_bulan  = st.selectbox("📅 Bulan", bulan_opts)

        type_opts = ["Semua", "Pemasukan", "Pengeluaran"]
        sel_type  = st.selectbox("💱 Jenis", type_opts)

        st.markdown("---")
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.markdown("### 📊 Info Data")
        st.caption(f"Awal  : {df_raw['date'].min().strftime('%d %b %Y')}")
        st.caption(f"Akhir : {df_raw['date'].max().strftime('%d %b %Y')}")
        st.caption(f"Total : {len(df_raw)} transaksi")
    else:
        sel_bulan = "Semua"
        sel_type  = "Semua"

if df_raw.empty:
    st.title(f"💰 Dashboard — {current_user}")
    st.info("Belum ada transaksi. Mulai catat lewat bot Telegram dengan /catat!")
    st.stop()

# ══════════════════════════════════════════════════════════
#  APPLY FILTERS
# ══════════════════════════════════════════════════════════
df = df_raw.copy()
if sel_bulan != "Semua":
    df = df[df["bulan"] == sel_bulan]
if sel_type != "Semua":
    df = df[df["type"] == sel_type.lower()]

inc_df        = df[df["type"] == "pemasukan"]
exp_df        = df[df["type"] == "pengeluaran"]
total_inc     = inc_df["amount"].sum()
total_exp     = exp_df["amount"].sum()
saldo         = total_inc - total_exp
n_trans       = len(df)
periode_label = sel_bulan if sel_bulan != "Semua" else "Semua Periode"

# ══════════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════════
st.markdown(f"# 💰 Dashboard — {current_user}")
st.caption(f"Periode: **{periode_label}**")
st.markdown("---")

# ══════════════════════════════════════════════════════════
#  METRICS
# ══════════════════════════════════════════════════════════
c1, c2, c3, c4 = st.columns(4)
c1.metric("💰 Total Pemasukan",   fmt_rp(total_inc))
c2.metric("💸 Total Pengeluaran", fmt_rp(total_exp))
c3.metric("💼 Saldo",             fmt_rp(saldo))
c4.metric("📝 Transaksi",         f"{n_trans} entri")
st.markdown("<br>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
#  CHARTS
# ══════════════════════════════════════════════════════════
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader("📈 Pemasukan vs Pengeluaran per Bulan")
    monthly = df.groupby(["bulan", "type"])["amount"].sum().reset_index()
    if not monthly.empty:
        fig = px.bar(monthly, x="bulan", y="amount", color="type", barmode="group",
                     color_discrete_map={"pemasukan": "#4ade80", "pengeluaran": "#f87171"},
                     labels={"amount": "Jumlah (Rp)", "bulan": "Bulan", "type": "Jenis"},
                     template="plotly_dark")
        fig.update_layout(height=320, plot_bgcolor="rgba(0,0,0,0)",
                          paper_bgcolor="rgba(0,0,0,0)", legend_title_text="",
                          margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("🍩 Pengeluaran per Kategori")
    if not exp_df.empty:
        cat_exp = exp_df.groupby("category")["amount"].sum().reset_index()
        fig2 = px.pie(cat_exp, values="amount", names="category", hole=0.5,
                      template="plotly_dark",
                      color_discrete_sequence=px.colors.qualitative.Bold)
        fig2.update_layout(height=320, paper_bgcolor="rgba(0,0,0,0)",
                           margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Tidak ada data pengeluaran.")

st.subheader("📉 Cashflow Kumulatif")
cf = df.copy()
cf["signed"]    = cf.apply(lambda r: r["amount"] if r["type"] == "pemasukan" else -r["amount"], axis=1)
cf              = cf.sort_values("date")
cf["kumulatif"] = cf["signed"].cumsum()
fig3 = go.Figure()
fig3.add_trace(go.Scatter(
    x=cf["date"], y=cf["kumulatif"], mode="lines+markers", fill="tozeroy",
    line=dict(color="#818cf8", width=2.5), fillcolor="rgba(129,140,248,0.15)",
    marker=dict(size=5, color="#818cf8"),
    hovertemplate="Tanggal: %{x|%d %b %Y}<br>Saldo: Rp %{y:,.0f}<extra></extra>"
))
fig3.update_layout(height=260, template="plotly_dark",
                   paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                   yaxis_title="Saldo (Rp)", margin=dict(l=0,r=0,t=10,b=0),
                   hovermode="x unified")
st.plotly_chart(fig3, use_container_width=True)

col3, col4 = st.columns(2)
with col3:
    st.subheader("📊 Tren Pengeluaran per Kategori")
    if not exp_df.empty:
        cat_mo = exp_df.groupby(["bulan", "category"])["amount"].sum().reset_index()
        fig4   = px.bar(cat_mo, x="bulan", y="amount", color="category", barmode="stack",
                        template="plotly_dark", labels={"amount": "Jumlah (Rp)", "bulan": "Bulan"},
                        color_discrete_sequence=px.colors.qualitative.Pastel)
        fig4.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)",
                           plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0))
        st.plotly_chart(fig4, use_container_width=True)

with col4:
    st.subheader("💰 Sumber Pemasukan per Bulan")
    if not inc_df.empty:
        inc_mo = inc_df.groupby(["bulan", "category"])["amount"].sum().reset_index()
        fig5   = px.bar(inc_mo, x="bulan", y="amount", color="category", barmode="stack",
                        template="plotly_dark", labels={"amount": "Jumlah (Rp)", "bulan": "Bulan"},
                        color_discrete_sequence=px.colors.qualitative.Set2)
        fig5.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)",
                           plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0))
        st.plotly_chart(fig5, use_container_width=True)

# ══════════════════════════════════════════════════════════
#  TABEL
# ══════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("📋 Rincian Transaksi")
show         = df[["date", "type", "category", "amount", "description"]].copy()
show.columns = ["Tanggal", "Jenis", "Kategori", "Jumlah", "Keterangan"]
show["Tanggal"] = show["Tanggal"].dt.strftime("%d/%m/%Y")
show["Jumlah"]  = show["Jumlah"].apply(fmt_rp)
show["Jenis"]   = show["Jenis"].str.title()
st.dataframe(show, use_container_width=True, height=320, hide_index=True)

# ══════════════════════════════════════════════════════════
#  DOWNLOAD
# ══════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("⬇️ Download Laporan")

label_period = sel_bulan.replace(" ", "_") if sel_bulan != "Semua" else "semua"
dl           = df[["date", "type", "category", "amount", "description"]].copy()
dl["date"]   = dl["date"].dt.strftime("%Y-%m-%d")
dl.columns   = ["Tanggal", "Jenis", "Kategori", "Jumlah", "Keterangan"]

d1, d2, d3 = st.columns(3)

with d1:
    pdf_bytes = generate_pdf(df, current_user, periode_label, total_inc, total_exp, saldo)
    st.download_button(
        "📄 Download PDF", data=pdf_bytes,
        file_name=f"laporan_{current_user}_{label_period}.pdf",
        mime="application/pdf", use_container_width=True
    )

with d2:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        dl.to_excel(writer, sheet_name="Transaksi", index=False)
        pd.DataFrame({
            "Keterangan": ["Total Pemasukan", "Total Pengeluaran", "Saldo", "Jumlah Transaksi"],
            "Nilai":      [fmt_rp(total_inc), fmt_rp(total_exp), fmt_rp(saldo), str(n_trans)]
        }).to_excel(writer, sheet_name="Ringkasan", index=False)
        cf_m           = df_raw.copy()
        if sel_bulan != "Semua":
            cf_m = cf_m[cf_m["bulan"] == sel_bulan]
        cf_sum         = cf_m.groupby("bulan").apply(
            lambda g: pd.Series({
                "Pemasukan":   g.loc[g["type"] == "pemasukan",   "amount"].sum(),
                "Pengeluaran": g.loc[g["type"] == "pengeluaran", "amount"].sum(),
            })
        ).reset_index()
        cf_sum.columns  = ["Bulan", "Pemasukan", "Pengeluaran"]
        cf_sum["Saldo"] = cf_sum["Pemasukan"] - cf_sum["Pengeluaran"]
        cf_sum.to_excel(writer, sheet_name="Cashflow Bulanan", index=False)
    st.download_button(
        "📊 Download Excel", data=buf.getvalue(),
        file_name=f"laporan_{current_user}_{label_period}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

with d3:
    csv = dl.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📋 Download CSV", data=csv,
        file_name=f"laporan_{current_user}_{label_period}.csv",
        mime="text/csv", use_container_width=True
    )

st.markdown("<br><br>", unsafe_allow_html=True)
st.caption(f"Dashboard Keuangan · {current_user} · Powered by Streamlit + Supabase + Telegram Bot")
