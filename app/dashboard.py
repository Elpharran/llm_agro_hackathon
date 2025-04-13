import streamlit as st
import pandas as pd
import plotly.express as px
import io


@st.cache_data
def load_data():
    df = pd.read_excel("примеры.xlsx")
    df["Дата"] = pd.to_datetime(df["Дата"], dayfirst=True)
    return df

df = load_data()

st.title("📊 Анализ результатов")

st.sidebar.header("Фильтры")
date_option = st.sidebar.radio(
    "Выберите режим фильтрации:",
    ("Вся история", "Выбрать период", "Сегодня")
)


if date_option == "Выбрать период":
    start_date = st.sidebar.date_input("Начальная дата", df["Дата"].min())
    end_date = st.sidebar.date_input("Конечная дата", df["Дата"].max())
    df = df[(df["Дата"] >= pd.to_datetime(start_date)) & (df["Дата"] <= pd.to_datetime(end_date))]

elif date_option == "Сегодня":
    today = pd.to_datetime("today").normalize()
    df = df[df["Дата"] == today]


output = io.BytesIO()

with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
    df["Дата"] = df["Дата"].dt.strftime("%d.%m.%Y") 
    df.to_excel(writer, index=False, sheet_name="Отчет")

output.seek(0)

st.sidebar.download_button(
    label="Скачать отчет за выбранный\n\nпериод в Excel",
    data=output,
    file_name=f"отчет_{start_date}_{end_date}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",type='primary'
)

tab1, tab2, tab3 = st.tabs(["🌱 По культуре", "📌 По операции", "🏢 По подразделениям"])


with tab1:
    selected_culture = st.selectbox("Выберите культуру:", sorted(df["Культура"].unique()))
    filtered_df = df[df["Культура"] == selected_culture]

    if filtered_df.empty:
        st.warning("Нет данных для выбранной культуры.")
    else:
        agg_df = filtered_df.groupby("Операция").agg({
            "За день, га": "sum",
            "С начала операции, га": "sum"
        }).reset_index().melt(id_vars="Операция", var_name="Тип показателя", value_name="Площадь, га")

        fig = px.bar(
            agg_df,
            x="Операция",
            y="Площадь, га",
            color="Тип показателя",
            barmode="stack",
            title=f"Сравнение показателей по операциям для культуры: {selected_culture}",
            text_auto=True,
            height=600
        )
        fig.update_layout(xaxis_title="Операция", yaxis_title="Площадь, га", title_x=0.5)
        st.plotly_chart(fig, use_container_width=True)


with tab2:
    operation_list = sorted(df["Операция"].unique())
    selected_operation = st.selectbox("Выберите операцию для анализа:", operation_list)

    op_df = df[df["Операция"] == selected_operation]
    group_op = op_df.groupby("Культура").agg({
        "За день, га": "sum",
        "С начала операции, га": "sum"
    }).reset_index().melt(id_vars="Культура", var_name="Тип показателя", value_name="Площадь, га")

    if group_op.empty:
        st.warning("Нет данных по выбранной операции.")
    else:
        fig_op = px.bar(
            group_op,
            x="Культура",
            y="Площадь, га",
            color="Тип показателя",
            barmode="stack",
            title=f"Сравнение культур по показателям операции: {selected_operation}",
            text_auto=True,
            height=600
        )
        fig_op.update_layout(xaxis_title="Культура", yaxis_title="Площадь, га", title_x=0.5)
        st.plotly_chart(fig_op, use_container_width=True)


with tab3:
    division_list = sorted(df["Подразделение"].unique())
    selected_division = st.selectbox("Выберите подразделение:", sorted(df["Подразделение"].unique()))


    div_df = df[df["Подразделение"] == selected_division]

    group_summary = div_df.groupby(["Операция", "Культура"])["За день, га"].sum().reset_index()


    if group_summary.empty:
        st.warning("Нет данных по выбранному подразделению.")
    else:
        fig_summary = px.bar(
            group_summary,
            x="Операция",
            y="За день, га",
            color="Культура",
            barmode="group",
            title=f"Общий объём работ по операциям и культурам — {selected_division}",
            labels={"За день, га": "Площадь, га"},
            height=600
        )
        fig_summary.update_layout(title_x=0.5)
        st.plotly_chart(fig_summary, use_container_width=True)
