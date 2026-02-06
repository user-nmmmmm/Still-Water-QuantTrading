from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

# =========================
# 交易窗口工具（北京时间）
# =========================
CN_TZ = ZoneInfo("Asia/Shanghai")


def to_cn(dt: datetime) -> datetime:
    """把引擎给的 current_dt 转为北京时间（尽量保留 tz-aware）"""
    if dt.tzinfo is None:
        # 如果引擎传进来是“无时区”，按北京时间解释
        return dt.replace(tzinfo=CN_TZ)
    return dt.astimezone(CN_TZ)


def in_trade_window_cn(
    dt_cn: datetime, start_h=20, start_m=0, end_h=8, end_m=0
) -> bool:
    """
    判断是否在交易窗口：20:00 到次日 08:00（跨天窗口）
    """
    t = dt_cn.time()
    start = time(start_h, start_m)
    end = time(end_h, end_m)
    # 跨天窗口：t >= start 或 t < end
    return (t >= start) or (t < end)


def session_id_cn(dt_cn: datetime, start_h=20, start_m=0) -> str:
    """
    session_id 用“窗口起点日期”标识：
    - 例如 2026-02-03 20:00 ~ 2026-02-04 08:00 的 session_id = "2026-02-03"
    - 对于次日 00:00~08:00，仍归属前一天的 session
    """
    start = time(start_h, start_m)
    if dt_cn.time() < time(8, 0):  # 00:00~07:59 属于上一天的 session
        return (dt_cn.date() - timedelta(days=1)).strftime("%Y-%m-%d")
    # 08:00~23:59：20:00 之后自然就是当天 session；但 08:00~19:59 不在窗口，也无所谓
    return dt_cn.date().strftime("%Y-%m-%d")


# =========================
# 初始化：加密版核心参数
# =========================
def m3_initialize_bigquant_run(context):
    # 你原来参数
    context.stock_count = 10
    context.stock_weights = 1 / context.stock_count
    context.change_num = 1

    # 交易窗口（北京时间）
    context.window_start_h, context.window_start_m = 20, 0
    context.window_end_h, context.window_end_m = 8, 0

    # 调仓频率：每 N 分钟允许调仓一次（建议 60 = 每小时）
    context.rebalance_every_minutes = 60
    context.last_rebalance_dt_cn = None

    # 窗口外是否允许触发风控（仅示例）
    context.enable_risk_orders_outside_window = True
    context.stop_loss_pct = 0.08  # 示例：-8% 止损（需你自己接入持仓成本口径）

    # 你的信号数据（示例假设已有 dt/position/instrument）
    # 注意：加密建议用 dt（精确到分钟/小时）而不是 date（自然日）
    context.my_data = context.data.copy()
    # 如果你仍然只有 date 字段，也能跑，但就会变成“每个自然日一套信号”
    # context.my_data = context.my_data.sort_values(["date", "position"])
    if "dt" in context.my_data.columns:
        context.my_data = context.my_data.sort_values(["dt", "position"])
    else:
        context.my_data = context.my_data.sort_values(["date", "position"])


# =========================
# （可选）窗口外风控示例
# =========================
def risk_management(context, data):
    """
    示例：窗口外只做风控，不开新仓、不加仓
    这里演示“止损”，你需要根据你平台提供的持仓成本字段来改。
    """
    # 取当前价的方式按你引擎的数据接口来（这里只写伪逻辑）
    for ins, pos in context.portfolio.positions.items():
        if pos.amount <= 0:
            continue

        # 下面 cost/price 字段名称需要你按实际引擎改
        # cost = pos.cost_basis or pos.avg_cost
        # price = data.current(ins, "close")  # 或 last/mark
        # if cost and price and (price / cost - 1) <= -context.stop_loss_pct:
        #     context.order_target(ins, 0)

        pass


# =========================
# 调仓函数：按你原逻辑（卖低分/补齐等权）
# =========================
def rebalance(context, data, ranker_prediction):
    # 当前持仓
    stock_now = {e: p for e, p in context.portfolio.positions.items() if p.amount > 0}
    stock_now_num = len(stock_now)

    # 当期应买入列表（多取几只防止买不了）
    try:
        buy_list = ranker_prediction.instrument.unique()[: context.stock_count + 3]
    except Exception:
        buy_list = []

    sell_num = 0

    if len(stock_now) > 0:
        # 1) 先卖出不在预测集的（比如你过滤条件变化、退市等）
        pred_set = set(ranker_prediction.instrument.unique())
        need_sell = [x for x in stock_now if x not in pred_set]
        for instrument in need_sell:
            rv = context.order_target(instrument, 0)
            if rv != 0:
                print(f"{instrument} 不在预测集卖出失败: {context.get_error_msg(rv)}")
                continue
            sell_num += 1

        # 2) 持有的票按预测排序，卖出得分低的（你原代码是反转后卖）
        #    注意：你的 ranker_prediction 只有 position/instrument；这里假设 position 越小越好
        held = ranker_prediction[
            ranker_prediction.instrument.apply(lambda x: x in stock_now)
        ]
        # position 越大越差 -> 先卖 position 最大的
        held_sorted = held.sort_values("position", ascending=False)[
            "instrument"
        ].tolist()

        for instrument in held_sorted:
            if sell_num >= context.change_num:
                break
            rv = context.order_target(instrument, 0)
            if rv != 0:
                print(f"{instrument} 卖出失败: {context.get_error_msg(rv)}")
                continue
            sell_num += 1
            stock_now_num -= 1
            # 同步更新持仓集合
            stock_now.pop(instrument, None)

    # 3) 有空位则买入补齐等权
    if len(buy_list) > 0 and stock_now_num < context.stock_count:
        buy_instruments = [i for i in buy_list if i not in stock_now]

        # 等权资金：可用现金 / 还差的仓位数
        slots_left = max(context.stock_count - stock_now_num, 1)
        cash_now = context.portfolio.cash / slots_left
        cash_for_buy = min(
            context.portfolio.portfolio_value * context.stock_weights, cash_now
        )

        for instrument in buy_instruments:
            if stock_now_num >= context.stock_count:
                break
            rv = context.order_value(instrument, cash_for_buy)
            if rv != 0:
                print(f"{instrument} 买入失败: {context.get_error_msg(rv)}")
                continue
            stock_now_num += 1


# =========================
# handle_data：只在 20:00-08:00 内调仓
# =========================
def m3_handle_data_bigquant_run(context, data):
    dt_cn = to_cn(data.current_dt)

    # 1) 是否在交易窗口
    in_window = in_trade_window_cn(
        dt_cn,
        context.window_start_h,
        context.window_start_m,
        context.window_end_h,
        context.window_end_m,
    )

    # 2) 窗口外：不调仓，只做（可选）风控
    if not in_window:
        if getattr(context, "enable_risk_orders_outside_window", False):
            risk_management(context, data)
        return

    # 3) 控制调仓频率（默认每 60 分钟一次）
    if context.last_rebalance_dt_cn is not None:
        if (dt_cn - context.last_rebalance_dt_cn) < timedelta(
            minutes=context.rebalance_every_minutes
        ):
            return

    # 4) 取本次 session 的信号（推荐你用 dt 对齐到小时/分钟）
    sid = session_id_cn(dt_cn, context.window_start_h, context.window_start_m)

    if "dt" in context.my_data.columns:
        # 建议：你的信号数据里 dt 是每小时/每15分钟一个时间戳
        # 这里用“最近一个不晚于当前时刻”的信号（避免未来函数）
        df = context.my_data
        # 若 dt 字段是字符串，先转 datetime（只做一次更好）
        if df["dt"].dtype == object:
            df = df.copy()
            df["dt"] = df["dt"].apply(lambda x: datetime.fromisoformat(x))

        # 转为北京时间再比较（若 dt 自带 tz，可直接 astimezone）
        def _to_cn_safe(x):
            if isinstance(x, datetime):
                return to_cn(x)
            return x

        df = df.copy()
        df["_dt_cn"] = df["dt"].apply(_to_cn_safe)

        # 只取当前 session 内、且不晚于当前时刻的最新一批信号
        # session 边界：sid 20:00 ~ sid+1 08:00
        sid_date = datetime.fromisoformat(sid).replace(tzinfo=CN_TZ)
        s_start = sid_date.replace(
            hour=context.window_start_h,
            minute=context.window_start_m,
            second=0,
            microsecond=0,
        )
        s_end = (sid_date + timedelta(days=1)).replace(
            hour=context.window_end_h,
            minute=context.window_end_m,
            second=0,
            microsecond=0,
        )

        df_sess = df[
            (df["_dt_cn"] >= s_start) & (df["_dt_cn"] < s_end) & (df["_dt_cn"] <= dt_cn)
        ]
        if df_sess.empty:
            return

        latest_dt = df_sess["_dt_cn"].max()
        ranker_prediction = df_sess[df_sess["_dt_cn"] == latest_dt].sort_values(
            "position"
        )
    else:
        # 兼容：只有自然日 date 信号（会变成窗口内“同一天用同一套信号”）
        # 这里用 session_id（sid）对应的 date
        ranker_prediction = context.my_data[context.my_data["date"] == sid].sort_values(
            "position"
        )
        if ranker_prediction.empty:
            return

    # 5) 执行调仓
    rebalance(context, data, ranker_prediction)

    # 6) 更新时间
    context.last_rebalance_dt_cn = dt_cn
