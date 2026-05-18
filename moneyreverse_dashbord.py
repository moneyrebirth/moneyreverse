"""
MoneyReverse v1 - MoneyForward限定ダッシュボード
使い方: streamlit run moneyreverse.py

対応ページ:
  - 💳 取引履歴
  - 📅 年次サマリー
  - 🗓️ 月次レビュー
"""

import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px

# household.db はこのスクリプトと同じディレクトリ
DB_PATH = Path(__file__).parent / "household.db"

st.set_page_config(
    page_title="MoneyReverse",
    page_icon="💰",
    layout="wide",
)

# ─── データ取得 ────────────────────────────────────────────────────────────────

@st.cache_data
def load_transactions() -> pd.DataFrame:
    """
    transactionsテーブルから全データを取得。
    MoneyForwardのCSVをインポートしたデータが対象。
    """
    with sqlite3.connect(DB_PATH) as conn:
        # テーブルが存在しない場合は空のDataFrameを返す
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'"
        ).fetchone()
        if not tables:
            return pd.DataFrame(columns=["source", "date", "description", "amount", "category", "memo"])

        df = pd.read_sql("""
            SELECT source, date, description, amount, category, memo
            FROM transactions
            WHERE source = 'moneyforward'
            ORDER BY date DESC
        """, conn, parse_dates=["date"])
    return df

def reload():
    load_transactions.clear()

# ─── サイドバー ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("💰 MoneyReverse")
    st.caption("v1 - MoneyForward edition")

    if st.button("🔄 データ再読み込み"):
        reload()
        st.rerun()

    st.divider()
    page = st.radio("ページ", ["💳 取引履歴", "📅 年次サマリー", "🗓️ 月次レビュー"])

tx = load_transactions()

if tx.empty:
    st.warning("データがありません。MoneyForwardのCSVをインポートしてください。")
    st.code("python3 mf_importer.py your_moneyforward.csv")
    st.stop()

# ─── 取引履歴 ──────────────────────────────────────────────────────────────────

if page == "💳 取引履歴":
    st.title("💳 取引履歴")

    col1, col2, col3 = st.columns(3)
    with col1:
        months = sorted(tx["date"].dt.to_period("M").unique(), reverse=True)
        sel_month = st.selectbox("月", ["全て"] + [str(m) for m in months])
    with col2:
        # 大項目一覧
        cats = sorted(tx["category"].dropna().str.split("/").str[0].unique())
        sel_cat = st.selectbox("カテゴリ", ["全て"] + cats)
    with col3:
        keyword = st.text_input("キーワード検索")

    filtered = tx.copy()
    if sel_month != "全て":
        filtered = filtered[filtered["date"].dt.to_period("M").astype(str) == sel_month]
    if sel_cat != "全て":
        filtered = filtered[filtered["category"].fillna("").str.startswith(sel_cat)]
    if keyword:
        filtered = filtered[filtered["description"].str.contains(keyword, na=False)]

    filtered = filtered.sort_values("date", ascending=False).copy()
    filtered["日付"] = filtered["date"].dt.strftime("%Y/%m/%d")
    filtered["金額"] = filtered["amount"].map(lambda x: f"¥{x:+,.0f}")
    filtered["カテゴリ"] = filtered["category"].fillna("未分類")

    st.dataframe(
        filtered[["日付", "description", "金額", "カテゴリ", "memo"]].rename(columns={
            "description": "摘要", "memo": "メモ"
        }),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(f"{len(filtered)}件")

# ─── 年次サマリー ──────────────────────────────────────────────────────────────

elif page == "📅 年次サマリー":
    st.title("📅 年次サマリー")

    # categoryカラム付きで全データ取得
    with sqlite3.connect(DB_PATH) as conn:
        txc = pd.read_sql("""
            SELECT date, amount, category
            FROM transactions
            WHERE source = 'moneyforward'
            ORDER BY date
        """, conn, parse_dates=["date"])

    txc["year"] = txc["date"].dt.year
    txc["ym"]   = txc["date"].dt.to_period("M").astype(str)

    # 振替除外（計算対象=0はインポート時にスキップ済み）
    expense_df = txc[txc["amount"] < 0].copy()
    expense_df["abs_amount"] = expense_df["amount"].abs()
    income_df  = txc[txc["amount"] > 0].copy()

    # ── 年別支出合計 ──
    st.subheader("年別支出合計")
    yearly = expense_df.groupby("year")["abs_amount"].sum().reset_index()
    yearly.columns = ["年", "支出合計"]
    fig_y = px.bar(yearly, x="年", y="支出合計",
                   labels={"支出合計": "支出（円）", "年": "年"})
    fig_y.update_traces(texttemplate="¥%{y:,.0f}", textposition="outside")
    fig_y.update_layout(yaxis_tickformat=",.0f", showlegend=False)
    st.plotly_chart(fig_y, use_container_width=True, key="yearly_bar")

    # ── 月別支出推移（全期間）──
    st.subheader("月別支出推移（全期間）")
    monthly = expense_df.groupby("ym")["abs_amount"].sum().reset_index()
    monthly.columns = ["月", "支出"]
    fig_m = px.line(monthly, x="月", y="支出",
                    labels={"支出": "支出（円）", "月": ""})
    fig_m.update_layout(yaxis_tickformat=",.0f")
    st.plotly_chart(fig_m, use_container_width=True, key="monthly_line")

    # ── カテゴリ別年次推移 ──
    st.subheader("カテゴリ別支出（年次）")
    cat_df = expense_df[expense_df["category"].notna() & (expense_df["category"] != "未分類")].copy()

    if cat_df.empty:
        st.info("カテゴリデータがありません")
    else:
        cat_df["大項目"] = cat_df["category"].str.split("/").str[0]
        top_cats = cat_df.groupby("大項目")["abs_amount"].sum().nlargest(8).index.tolist()
        cat_yearly = cat_df[cat_df["大項目"].isin(top_cats)].groupby(
            ["year", "大項目"]
        )["abs_amount"].sum().reset_index()
        cat_yearly.columns = ["年", "カテゴリ", "支出"]
        fig_c = px.bar(cat_yearly, x="年", y="支出", color="カテゴリ",
                       barmode="stack",
                       labels={"支出": "支出（円）", "年": "年"})
        fig_c.update_layout(yaxis_tickformat=",.0f", legend_title="カテゴリ")
        st.plotly_chart(fig_c, use_container_width=True, key="cat_yearly_bar")

    # ── 年別サマリーテーブル ──
    st.subheader("年別サマリー")
    yr_exp     = expense_df.groupby("year")["abs_amount"].sum()
    yr_inc     = income_df.groupby("year")["amount"].sum()
    yr_summary = pd.DataFrame({"支出": yr_exp, "収入": yr_inc}).fillna(0).astype(int)
    yr_summary["収支"]    = yr_summary["収入"] - yr_summary["支出"]
    yr_summary.index.name = "年"
    yr_summary = yr_summary.sort_index(ascending=False)
    yr_summary["支出"] = yr_summary["支出"].map(lambda x: f"¥{x:,.0f}")
    yr_summary["収入"] = yr_summary["収入"].map(lambda x: f"¥{x:,.0f}")
    yr_summary["収支"] = yr_summary["収支"].map(lambda x: f"¥{x:+,.0f}")
    st.dataframe(yr_summary, use_container_width=True)

# ─── 月次レビュー ──────────────────────────────────────────────────────────────

elif page == "🗓️ 月次レビュー":
    st.title("🗓️ 月次レビュー")

    # 月ナビゲーション
    today = pd.Timestamp.today()
    if "review_year"  not in st.session_state: st.session_state.review_year  = today.year
    if "review_month" not in st.session_state: st.session_state.review_month = today.month

    col_prev, col_title, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("◀ 前月"):
            if st.session_state.review_month == 1:
                st.session_state.review_month = 12
                st.session_state.review_year -= 1
            else:
                st.session_state.review_month -= 1
            st.rerun()
    with col_title:
        st.markdown(
            f"<h3 style='text-align:center'>"
            f"{st.session_state.review_year}/{st.session_state.review_month:02d}"
            f"</h3>",
            unsafe_allow_html=True
        )
    with col_next:
        if st.button("次月 ▶"):
            if st.session_state.review_month == 12:
                st.session_state.review_month = 1
                st.session_state.review_year += 1
            else:
                st.session_state.review_month += 1
            st.rerun()

    yr  = st.session_state.review_year
    mon = st.session_state.review_month

    with sqlite3.connect(DB_PATH) as conn:
        month_cat = pd.read_sql(f"""
            SELECT date, description, amount, category, memo
            FROM transactions
            WHERE source = 'moneyforward'
              AND strftime('%Y', date) = '{yr:04d}'
              AND strftime('%m', date) = '{mon:02d}'
            ORDER BY date DESC
        """, conn, parse_dates=["date"])

    income  = month_cat[month_cat["amount"] > 0]["amount"].sum()
    expense = month_cat[month_cat["amount"] < 0]["amount"].sum()
    balance = income + expense

    col1, col2, col3 = st.columns(3)
    col1.metric("当月収入", f"¥{income:,.0f}")
    col2.metric("当月支出", f"¥{abs(expense):,.0f}")
    col3.metric("当月収支", f"¥{balance:+,.0f}",
                delta_color="normal" if balance >= 0 else "inverse")

    st.divider()

    exp_df = month_cat[month_cat["amount"] < 0].copy()
    exp_df["abs_amount"] = exp_df["amount"].abs()
    exp_df["大項目"] = exp_df["category"].fillna("未分類").str.split("/").str[0]
    exp_df["中項目"] = exp_df["category"].fillna("").apply(
        lambda x: x.split("/")[1] if "/" in str(x) else ""
    )

    if exp_df.empty:
        st.info("この月の支出データがありません")
    else:
        total_exp = exp_df["abs_amount"].sum()
        col_l, col_r = st.columns([3, 2])

        with col_l:
            st.subheader("カテゴリ別支出")
            major_grp = exp_df.groupby("大項目")["abs_amount"].sum().sort_values(ascending=False)

            for major, major_total in major_grp.items():
                pct = major_total / total_exp * 100
                with st.expander(f"**{major}**　¥{major_total:,.0f}　({pct:.1f}%)"):
                    # 中項目合計
                    minor_grp = exp_df[exp_df["大項目"] == major].groupby(
                        exp_df["中項目"].replace("", "（なし）")
                    )["abs_amount"].sum().sort_values(ascending=False)
                    for minor, minor_total in minor_grp.items():
                        st.markdown(f"　{minor}　¥{minor_total:,.0f}")

                    # 明細
                    detail = exp_df[exp_df["大項目"] == major][
                        ["date", "description", "abs_amount"]
                    ].copy()
                    detail["date"] = detail["date"].dt.strftime("%m/%d")
                    detail.columns = ["日付", "摘要", "金額"]
                    detail["金額"] = detail["金額"].map(lambda x: f"¥{x:,.0f}")
                    st.dataframe(detail, use_container_width=True, hide_index=True)

        with col_r:
            st.subheader("支出内訳")
            fig = px.pie(
                major_grp.reset_index(),
                values="abs_amount",
                names="大項目",
                hole=0.4,
            )
            fig.update_traces(textposition="inside", textinfo="percent")
            fig.update_layout(
                showlegend=True,
                legend=dict(orientation="v", x=1.05, y=0.5),
                margin=dict(t=20, b=20, l=20, r=120)
            )
            st.plotly_chart(fig, use_container_width=True, key="monthly_pie")
            st.metric("支出合計", f"¥{total_exp:,.0f}")
