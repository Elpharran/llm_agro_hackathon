import streamlit as st
import pandas as pd
import plotly.express as px
import io

from streamlit import session_state as ss

# для демо дашборда
try:
    from db.interaction import get_all_operations, update_record_by_id
    ss.df = get_all_operations()
    ss.demo = False
except ModuleNotFoundError:
    ss.demo = True
    ss.df = pd.read_excel("app/примеры.xlsx")
    ss.df["Дата"] = pd.to_datetime(ss.df["Дата"], dayfirst=True)
    ss.df["id"] = range(len(ss.df))
    ss.df = ss.df[[ss.df.columns.tolist()[-1]] + ss.df.columns.tolist()[:-1]]


def load_session_state():
    ss.today = pd.to_datetime("today").normalize()
    if "start_date" not in ss:
        ss.start_date = ss.today
    if "end_date" not in ss:
        ss.end_date = ss.today


def create_sidebar():
    st.sidebar.header("Фильтры")
    ss.date_option = st.sidebar.radio(
        "Выберите режим фильтрации:", ("Вся история", "Выбрать период", "Сегодня")
    )

    if ss.date_option == "Выбрать период":
        ss.start_date = st.sidebar.date_input("Начальная дата", ss.df["Дата"].min())
        ss.end_date = st.sidebar.date_input("Конечная дата", ss.df["Дата"].max())
        ss.df = ss.df[
            (ss.df["Дата"] >= pd.to_datetime(ss.start_date))
            & (ss.df["Дата"] <= pd.to_datetime(ss.end_date))
        ]

    elif ss.date_option == "Сегодня":

        ss.df = ss.df[ss.df["Дата"] == ss.today]

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        ss.df["Дата"] = ss.df["Дата"].dt.strftime("%d.%m.%Y")
        ss.df.to_excel(writer, index=False, sheet_name="Отчет")

    output.seek(0)

    report_name = (
        f"Отчёт {ss.start_date} - {ss.end_date}.xlsx"
        if ss.date_option == "Выбрать период"
        else f"Отчёт {ss.today}"
    )
    st.sidebar.download_button(
        label="Скачать отчет за выбранный\n\nпериод в Excel",
        data=output,
        file_name=report_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )


def cultures_figure():
    selected_culture = st.selectbox(
        "Выберите культуру:", sorted(ss.df["Культура"].unique())
    )
    filtered_df = ss.df[ss.df["Культура"] == selected_culture]

    if filtered_df.empty:
        st.warning("Нет данных для выбранной культуры.")
    else:
        agg_df = (
            filtered_df.groupby("Операция")
            .agg({"За день, га": "sum", "С начала операции, га": "sum"})
            .reset_index()
            .melt(
                id_vars="Операция", var_name="Тип показателя", value_name="Площадь, га"
            )
        )

        fig = px.bar(
            agg_df,
            x="Операция",
            y="Площадь, га",
            color="Тип показателя",
            barmode="stack",
            title=f"Сравнение показателей по операциям для культуры: {selected_culture}",
            text_auto=True,
            height=600,
        )
        fig.update_layout(
            xaxis_title="Операция", yaxis_title="Площадь, га", title_x=0.5
        )
        st.plotly_chart(fig, use_container_width=True)


def operations_figure():
    operation_list = sorted(ss.df["Операция"].unique())
    selected_operation = st.selectbox("Выберите операцию:", operation_list)

    op_df = ss.df[ss.df["Операция"] == selected_operation]
    group_op = (
        op_df.groupby("Культура")
        .agg({"За день, га": "sum", "С начала операции, га": "sum"})
        .reset_index()
        .melt(id_vars="Культура", var_name="Тип показателя", value_name="Площадь, га")
    )

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
            height=600,
        )
        fig_op.update_layout(
            xaxis_title="Культура", yaxis_title="Площадь, га", title_x=0.5
        )
        st.plotly_chart(fig_op, use_container_width=True)


def divisions_figure():
    division_list = sorted(ss.df["Подразделение"].unique())
    selected_division = st.selectbox("Выберите подразделение:", division_list)

    div_df = ss.df[ss.df["Подразделение"] == selected_division]

    group_summary = (
        div_df.groupby(["Операция", "Культура"])["За день, га"].sum().reset_index()
    )
    group_summary = group_summary.fillna(0)
    group_summary = group_summary[group_summary["За день, га"] > 0]

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
            text_auto=True,
            height=600,
        )
        fig_summary.update_layout(title_x=0.5, bargap=0.0, bargroupgap=0.0)
        st.plotly_chart(fig_summary, use_container_width=True)

def manage_data():
    st.markdown(
        "**При необходимости изменения данных отредактируйте требуемые значения в ячейках таблицы**"
    )

    # Используем data_editor для редактирования
    edited_df = st.data_editor(
        ss.df,
        use_container_width=True,
        num_rows="fixed",
        hide_index=True,
        disabled=['id']
    )

    if st.button("**Обновить таблицу в Базе Данных**", type='primary'):
        changes = edited_df.compare(ss.df)
        updates = {}

        for idx in changes.index:
            row_changes = changes.loc[idx]
            new_values = {}

            for col in edited_df.columns:
                if (col, 'self') in row_changes and (col, 'other') in row_changes:
                    new_value = row_changes[(col, 'self')]
                    old_value = row_changes[(col, 'other')]
                    if pd.notna(new_value) and new_value != old_value:
                        new_values[col] = new_value

            if new_values:
                row_id = int(edited_df.loc[idx, "id"])  # <-- приведение к int
                updates[row_id] = new_values

        if updates:
            if not ss.demo:
                update_record_by_id(list(updates.keys()), list(updates.values()))
            st.success('Данные успешно обновлены', icon='✅')
            ss.df = edited_df
    else:
        st.info('Нет изменений для обновления.')

if __name__ == "__main__":
    st.set_page_config(page_title="Отчёты", page_icon="🌾")
    st.title("📊 Отчётность")
    load_session_state()
    if not ss.df.empty:
        create_sidebar()
        tab1, tab2, tab3, tab4 = st.tabs(
            [
                "📝 Все данные",
                "🌱 График по культурам",
                "📌 График по операциям",
                "🏢 График по подразделениям",
            ]
        )
        with tab1:
            manage_data()
        with tab2:
            divisions_figure()
        with tab3:
            operations_figure()
        with tab4:
            cultures_figure()
    else:
        st.warning('Данные в таблице отсутствуют.')