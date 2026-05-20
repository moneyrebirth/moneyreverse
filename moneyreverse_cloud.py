"""
MoneyReverse v1.1 - Streamlit Cloud版
DBなし、CSVアップロードで即解析

使い方:
  streamlit run moneyreverse_cloud.py

Streamlit Cloud:
  share.streamlit.io でGitHubリポジトリを連携するだけ
"""

import io
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(
    page_title="MoneyReverse",
    page_icon="💰",
    layout="wide",
)

# ─── ヘッダー ──────────────────────────────────────────────────────────────────

st.title("💰 MoneyReverse")
st.caption("MoneyForwardのCSVをアップロードして家計簿を可視化")

# ─── CSVアップロード ───────────────────────────────────────────────────────────

st.divider()
uploaded_files = st.file_uploader(
    "MoneyForwardのCSVをアップロード（複数可）",
    type="csv",
    accept_multiple_files=True,
    help="MoneyForward ME → 家計簿 → 収支内訳 → CSVダウンロード",
)

if not uploaded_files:
    st.info("👆 MoneyForwardからエクスポートしたCSVをアップロードしてください")

    with st.expander("📖 CSVのエクスポート方法"):
        st.markdown("""
1. [MoneyForward ME](https://moneyforward.com) にログイン
2. 「家計簿」→「収支内訳」を開く
3. 右上の「CSVダウンロード」をクリック
4. 期間を選択してダウンロード
5. このページにドラッグ＆ドロップ

複数月分を一度にアップロードできます。
        """)

    with st.expander("🔒 プライバシーについて"):
        st.markdown("""
- アップロードされたデータはサーバーに保存されません
- セッション終了時にデータは消去されます
- データはブラウザとStreamlitサーバー間でのみ処理されます
        """)
    st.stop()

# ─── データ読み込み ────────────────────────────────────────────────────────────

@st.cache_data
def load_csv(files) -> pd.DataFrame:
    """
    複数CSVを結合してDataFrameを返す。
    Shift_JIS / UTF-8 自動判定。
    振替（計算対象=0）は除外。
    """
    dfs = []
    for f in files:
        raw = f.read()
        # 文字コード自動判定
        for enc in ("shift_jis", "utf-8-sig", "utf-8"):
            try:
                text = raw.decode(enc)
                df   = pd.read_csv(io.StringIO(text), dtype=str)
                dfs.append(df)
                break
            except (UnicodeDecodeError, Exception):
                continue

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)

    # 列名の正規化
    combined.columns = combined.columns.str.strip()

    # 必要列の確認
    required = ["日付", "内容", "金額（円）", "大項目", "中項目"]
    for col in required:
        if col not in combined.columns:
            st.error(f"❌ CSVに「{col}」列が見つかりません。MoneyForwardのCSVか確認してください。")
            return pd.DataFrame()

    # 振替除外（計算対象=0）
    if "計算対象" in combined.columns:
        combined = combined[combined["計算対象"].str.strip() == "1"]

    # 型変換
    combined["日付"] = pd.to_datetime(combined["日付"], errors="coerce")
    combined["金額"] = combined["金額（円）"].str.replace(",", "").str.strip().astype(float, errors="ignore")
    combined         = combined.dropna(subset=["日付", "金額"])
    combined["金額"] = combined["金額"].astype(int)

    # カテゴリ結合
    combined["カテゴリ"] = combined.apply(
        lambda r: f"{r['大項目']}/{r['中項目']}"
        if r["中項目"].strip() and r["中項目"].strip() != r["大項目"].strip()
        else r["大項目"],
        axis=1
    )
    combined["大項目"] = combined["大項目"].str.strip()
    combined["年"]    = combined["日付"].dt.year
    combined["月"]    = combined["日付"].dt.to_period("M").astype(str)

    return combined.sort_values("日付", ascending=False)

df = load_csv(tuple(uploaded_files))

if df.empty:
    st.stop()

st.success(f"✅ {len(uploaded_files)}ファイル / {len(df):,}件 読み込み完了")

# ─── ページ選択 ────────────────────────────────────────────────────────────────

page = st.sidebar.radio(
    "ページ",
    ["🗓️ 月次レビュー", "📅 年次サマリー", "💳 取引履歴"]
)
st.sidebar.divider()
st.sidebar.caption(f"📊 {len(df):,}件のデータ")
st.sidebar.caption(f"📅 {df['日付'].min().strftime('%Y/%m')} 〜 {df['日付'].max().strftime('%Y/%m')}")

expense_df = df[df["金額"] < 0].copy()
expense_df["金額絶対値"] = expense_df["金額"].abs()
income_df  = df[df["金額"] > 0].copy()

# ─── 月次レビュー ──────────────────────────────────────────────────────────────

if page == "🗓️ 月次レビュー":
    st.title("🗓️ 月次レビュー")

    # 月ナビゲーション
    months = sorted(df["月"].unique(), reverse=True)

    if "month_idx" not in st.session_state:
        st.session_state.month_idx = 0
    st.session_state.month_idx = max(0, min(st.session_state.month_idx, len(months) - 1))

    col_prev, col_sel, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("◀ 前月", disabled=st.session_state.month_idx >= len(months) - 1):
            st.session_state.month_idx += 1
            st.rerun()
    with col_sel:
        sel = st.selectbox("月を選択", months, index=st.session_state.month_idx, label_visibility="collapsed")
        if sel != months[st.session_state.month_idx]:
            st.session_state.month_idx = months.index(sel)
            st.rerun()
    with col_next:
        if st.button("次月 ▶", disabled=st.session_state.month_idx <= 0):
            st.session_state.month_idx -= 1
            st.rerun()

    sel_month = months[st.session_state.month_idx]

    st.markdown(f"<h3 style='text-align:center'>{sel_month}</h3>", unsafe_allow_html=True)

    month_df  = df[df["月"] == sel_month]
    m_expense = month_df[month_df["金額"] < 0]["金額"].sum()
    m_income  = month_df[month_df["金額"] > 0]["金額"].sum()
    m_balance = m_income + m_expense

    col1, col2, col3 = st.columns(3)
    col1.metric("当月収入", f"¥{m_income:,.0f}")
    col2.metric("当月支出", f"¥{abs(m_expense):,.0f}")
    col3.metric("当月収支", f"¥{m_balance:+,.0f}")

    st.divider()

    m_exp_df = month_df[month_df["金額"] < 0].copy()
    m_exp_df["金額絶対値"] = m_exp_df["金額"].abs()

    if m_exp_df.empty:
        st.info("この月の支出データがありません")
    else:
        total_exp = m_exp_df["金額絶対値"].sum()
        col_l, col_r = st.columns([3, 2])

        with col_l:
            st.subheader("カテゴリ別支出")
            major_grp = m_exp_df.groupby("大項目")["金額絶対値"].sum().sort_values(ascending=False)

            for major, major_total in major_grp.items():
                pct = major_total / total_exp * 100
                with st.expander(f"**{major}**　¥{major_total:,.0f}　({pct:.1f}%)"):
                    detail = m_exp_df[m_exp_df["大項目"] == major][
                        ["日付", "内容", "金額絶対値", "カテゴリ"]
                    ].copy()
                    detail["日付"] = detail["日付"].dt.strftime("%m/%d")
                    detail["金額"] = detail["金額絶対値"].map(lambda x: f"¥{x:,.0f}")
                    st.dataframe(
                        detail[["日付", "内容", "金額", "カテゴリ"]],
                        use_container_width=True,
                        hide_index=True,
                    )

        with col_r:
            st.subheader("支出内訳")
            fig = px.pie(
                major_grp.reset_index(),
                values="金額絶対値",
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

# ─── 年次サマリー ──────────────────────────────────────────────────────────────

elif page == "📅 年次サマリー":
    st.title("📅 年次サマリー")

    # 年別支出合計
    st.subheader("年別支出合計")
    yearly = expense_df.groupby("年")["金額絶対値"].sum().reset_index()
    yearly.columns = ["年", "支出合計"]
    fig_y = px.bar(yearly, x="年", y="支出合計",
                   labels={"支出合計": "支出（円）", "年": "年"})
    fig_y.update_traces(texttemplate="¥%{y:,.0f}", textposition="outside")
    fig_y.update_layout(yaxis_tickformat=",.0f", showlegend=False)
    st.plotly_chart(fig_y, use_container_width=True, key="yearly_bar")

    # 月別支出推移
    st.subheader("月別支出推移")
    monthly = expense_df.groupby("月")["金額絶対値"].sum().reset_index()
    monthly.columns = ["月", "支出"]
    fig_m = px.line(monthly, x="月", y="支出",
                    labels={"支出": "支出（円）", "月": ""})
    fig_m.update_layout(yaxis_tickformat=",.0f")
    st.plotly_chart(fig_m, use_container_width=True, key="monthly_line")

    # カテゴリ別年次推移
    st.subheader("カテゴリ別支出（年次）")
    cat_df   = expense_df[expense_df["大項目"] != "未分類"].copy()
    top_cats = cat_df.groupby("大項目")["金額絶対値"].sum().nlargest(8).index.tolist()
    cat_yearly = cat_df[cat_df["大項目"].isin(top_cats)].groupby(
        ["年", "大項目"]
    )["金額絶対値"].sum().reset_index()
    cat_yearly.columns = ["年", "カテゴリ", "支出"]
    fig_c = px.bar(cat_yearly, x="年", y="支出", color="カテゴリ",
                   barmode="stack",
                   labels={"支出": "支出（円）", "年": "年"})
    fig_c.update_layout(yaxis_tickformat=",.0f", legend_title="カテゴリ")
    st.plotly_chart(fig_c, use_container_width=True, key="cat_yearly")

    # 年別サマリーテーブル
    st.subheader("年別サマリー")
    yr_exp     = expense_df.groupby("年")["金額絶対値"].sum()
    yr_inc     = income_df.groupby("年")["金額"].sum()
    yr_summary = pd.DataFrame({"支出": yr_exp, "収入": yr_inc}).fillna(0).astype(int)
    yr_summary["収支"]    = yr_summary["収入"] - yr_summary["支出"]
    yr_summary.index.name = "年"
    yr_summary = yr_summary.sort_index(ascending=False)
    yr_summary["支出"] = yr_summary["支出"].map(lambda x: f"¥{x:,.0f}")
    yr_summary["収入"] = yr_summary["収入"].map(lambda x: f"¥{x:,.0f}")
    yr_summary["収支"] = yr_summary["収支"].map(lambda x: f"¥{x:+,.0f}")
    st.dataframe(yr_summary, use_container_width=True)

# ─── 取引履歴 ──────────────────────────────────────────────────────────────────

elif page == "💳 取引履歴":
    st.title("💳 取引履歴")

    col1, col2, col3 = st.columns(3)
    with col1:
        months    = ["全て"] + sorted(df["月"].unique(), reverse=True)
        sel_month = st.selectbox("月", months)
    with col2:
        cats    = ["全て"] + sorted(df["大項目"].unique())
        sel_cat = st.selectbox("カテゴリ", cats)
    with col3:
        keyword = st.text_input("キーワード検索")

    filtered = df.copy()
    if sel_month != "全て":
        filtered = filtered[filtered["月"] == sel_month]
    if sel_cat != "全て":
        filtered = filtered[filtered["大項目"] == sel_cat]
    if keyword:
        filtered = filtered[filtered["内容"].str.contains(keyword, na=False)]

    filtered["日付表示"] = filtered["日付"].dt.strftime("%Y/%m/%d")
    filtered["金額表示"] = filtered["金額"].map(lambda x: f"¥{x:+,.0f}")

    st.dataframe(
        filtered[["日付表示", "内容", "金額表示", "カテゴリ"]].rename(columns={
            "日付表示": "日付", "金額表示": "金額"
        }),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(f"{len(filtered):,}件")
