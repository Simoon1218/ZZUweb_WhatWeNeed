"""FastAPI application for ZZUweb_WhatWeNeed."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import demo_data
from .config import settings
from .session import UserSession, session_store
from .zzu_client import (
    ZZUApiError,
    ZZUClient,
    ZZUMFARequiredError,
    find_available_classroom,
    get_today_date_str,
    utc_plus_8,
)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="ZZU WhatWeNeed",
    description="郑州大学移动校园一站式网页端（基于 TorCroft/ZZU-API）",
    version="1.0.0",
)


# ------------------------------------------------------------------
# Error Handling
# ------------------------------------------------------------------
@app.exception_handler(ZZUMFARequiredError)
async def zzu_mfa_required_handler(
    _request: Request, exc: ZZUMFARequiredError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "mfa_required": True,
            "mfa_state": exc.mfa_state,
            "mfa_data": exc.mfa_data,
        },
    )


@app.exception_handler(ZZUApiError)
async def zzu_api_error_handler(_request: Request, exc: ZZUApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


# ------------------------------------------------------------------
# Request Schemas
# ------------------------------------------------------------------
class LoginRequest(BaseModel):
    account: str = Field(..., min_length=1, max_length=64, description="学号")
    password: str = Field("", max_length=128, description="移动校园密码")
    user_token: str = Field("", max_length=4096, description="可选：直接填入已有 UserToken")
    mfa_state: str = Field("", max_length=512, description="可选：已完成二次验证的 mfaState")


class MFASendRequest(BaseModel):
    mfa_state: str = Field(..., min_length=1, max_length=512)
    mfa_type: str = Field("securephone", max_length=64)


class MFAVerifyRequest(BaseModel):
    account: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)
    mfa_state: str = Field(..., min_length=1, max_length=512)
    gid: str = Field("", max_length=256)
    code: str = Field(..., min_length=1, max_length=32)
    mfa_type: str = Field("securephone", max_length=64)


class TransferRequest(BaseModel):
    from_id: str = Field("", max_length=64, description="付款人学号（默认当前登录学号）")
    to_id: str = Field(..., min_length=3, max_length=64, description="收款人学号")
    amount: float = Field(..., gt=0, le=5000, description="转账金额（元）")
    card_password: str = Field(..., min_length=4, max_length=32, description="校园卡密码")


# ------------------------------------------------------------------
# Auth Helpers
# ------------------------------------------------------------------
def _is_https(request: Request) -> bool:
    if settings.cookie_secure:
        return True
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto == "https"


def _set_session_cookie(response: Response, request: Request, signed_sid: str) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=signed_sid,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
        max_age=settings.session_ttl_seconds,
        path="/",
    )


def require_session(request: Request) -> UserSession:
    signed_sid = request.cookies.get(settings.cookie_name)
    sess = session_store.get(signed_sid)
    if not sess:
        raise HTTPException(status_code=401, detail="未登录或会话已过期，请重新登录")
    return sess


def _session_info(sess: UserSession) -> dict[str, Any]:
    return {
        "authenticated": True,
        "account": sess.account,
        "demo_mode": sess.demo_mode,
        "has_jw_token": bool(sess.jw_token) or sess.demo_mode,
        "has_ecard_token": bool(sess.ecard_access_token) or sess.demo_mode,
        "today": get_today_date_str(),
    }


# ------------------------------------------------------------------
# Health & Auth Routes
# ------------------------------------------------------------------
@app.get("/api/health")
def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "zzuweb-whatweneed",
        "date": get_today_date_str(),
    }


@app.get("/api/auth/me")
def get_me(request: Request) -> dict[str, Any]:
    signed_sid = request.cookies.get(settings.cookie_name)
    sess = session_store.get(signed_sid)
    if not sess:
        return {"authenticated": False, "today": get_today_date_str()}
    return _session_info(sess)


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    account = payload.account.strip()
    user_token = payload.user_token.strip()

    if not user_token:
        if not payload.password:
            raise HTTPException(status_code=400, detail="请输入密码，或使用已有 UserToken 登录")
        client = ZZUClient()
        user_token = client.login(
            account,
            payload.password,
            mfa_state=payload.mfa_state,
        )

    sess, signed_sid = session_store.create(
        account=account,
        user_token=user_token,
        demo_mode=False,
    )

    # Pre-warm JW token so we validate UserToken right away if possible
    warnings: list[str] = []
    try:
        ZZUClient(sess).get_jw_token()
    except ZZUApiError as exc:
        if payload.user_token.strip():
            # When logging in via pasted UserToken, fail fast if token is invalid
            session_store.delete(signed_sid)
            raise
        warnings.append(f"教务令牌预获取失败（可稍后重试）：{exc.message}")

    _set_session_cookie(response, request, signed_sid)
    info = _session_info(sess)
    if warnings:
        info["warnings"] = warnings
    return info


@app.post("/api/auth/mfa/send")
def send_mfa_code(payload: MFASendRequest) -> dict[str, Any]:
    client = ZZUClient()
    result = client.init_mfa_sms(mfa_state=payload.mfa_state, mfa_type=payload.mfa_type)
    return {"ok": True, **result}


@app.post("/api/auth/mfa/verify")
def verify_mfa_and_login(
    payload: MFAVerifyRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    client = ZZUClient()
    client.verify_mfa_code(
        mfa_state=payload.mfa_state,
        code=payload.code,
        gid=payload.gid,
        mfa_type=payload.mfa_type,
    )
    user_token = client.login(
        payload.account.strip(),
        payload.password,
        mfa_state=payload.mfa_state,
    )
    sess, signed_sid = session_store.create(
        account=payload.account.strip(),
        user_token=user_token,
        demo_mode=False,
    )
    warnings: list[str] = []
    try:
        ZZUClient(sess).get_jw_token()
    except ZZUApiError as exc:
        warnings.append(f"教务令牌预获取失败（可稍后重试）：{exc.message}")

    _set_session_cookie(response, request, signed_sid)
    info = _session_info(sess)
    if warnings:
        info["warnings"] = warnings
    return info


@app.post("/api/auth/demo")
def login_demo(request: Request, response: Response) -> dict[str, Any]:
    sess, signed_sid = session_store.create(
        account="202300000001",
        demo_mode=True,
    )
    _set_session_cookie(response, request, signed_sid)
    return _session_info(sess)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str, Any]:
    signed_sid = request.cookies.get(settings.cookie_name)
    session_store.delete(signed_sid)
    response.delete_cookie(key=settings.cookie_name, path="/")
    return {"ok": True}


# ------------------------------------------------------------------
# JW Academic Routes
# ------------------------------------------------------------------
@app.get("/api/jw/campuses")
def get_campuses(sess: UserSession = Depends(require_session)) -> dict[str, Any]:
    if sess.demo_mode:
        return {"data": demo_data.get_demo_campuses(), "demo_mode": True}
    data = ZZUClient(sess).get_campus_building()
    return {"data": data, "demo_mode": False}


@app.get("/api/jw/classrooms")
def get_classrooms(
    building_id: str = Query(..., description="教学楼 ID，例如北1为 5"),
    date: str | None = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    floor: str | None = Query(None, description="楼层筛选（可选）"),
    periods: str | None = Query(None, description="逗号分隔的节次，例如 1,2,5,6"),
    sess: UserSession = Depends(require_session),
) -> dict[str, Any]:
    target_date = (date or "").strip() or get_today_date_str()

    period_list: list[int] = []
    if periods:
        for item in periods.split(","):
            item = item.strip()
            if item.isdigit():
                val = int(item)
                if 1 <= val <= 12:
                    period_list.append(val)

    if sess.demo_mode:
        raw = demo_data.get_demo_rooms(building_id, target_date)
    else:
        raw = ZZUClient(sess).get_room_data_by_building_id(building_id, target_date)

    # Extract rooms list from upstream payload
    rooms: list[dict[str, Any]] = []
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        rooms = raw[0].get("rooms") or []
    elif isinstance(raw, dict):
        rooms = raw.get("rooms") or []

    filtered = find_available_classroom(rooms, floor=floor, periods=period_list)
    floors = sorted(
        {str(r.get("floor")) for r in rooms if r.get("floor") is not None},
        key=lambda x: int(x) if x.lstrip("-").isdigit() else 999,
    )

    return {
        "building_id": building_id,
        "date": target_date,
        "floor": floor or "",
        "periods": period_list,
        "floors": floors,
        "total_rooms": len(rooms),
        "available_count": len(filtered),
        "available_rooms": filtered,
        "all_rooms": rooms,
        "demo_mode": sess.demo_mode,
    }


@app.get("/api/jw/semesters")
def get_semesters(
    biz_type_id: str = Query("1", description="学生类别，1=本科生"),
    sess: UserSession = Depends(require_session),
) -> dict[str, Any]:
    if sess.demo_mode:
        return {"data": demo_data.get_demo_semesters(), "demo_mode": True}
    data = ZZUClient(sess).get_semester(biz_type_id=biz_type_id)
    return {"data": data, "demo_mode": False}


@app.get("/api/jw/timetable")
def get_timetable(
    semester_id: str = Query(..., description="学期 ID"),
    campus_id: str = Query("2", description="校区 ID，默认主校区 2"),
    sess: UserSession = Depends(require_session),
) -> dict[str, Any]:
    if sess.demo_mode:
        return {"data": demo_data.get_demo_timetable(), "demo_mode": True}
    data = ZZUClient(sess).get_time_table(semester_id=semester_id, campus_id=campus_id)
    return {"data": data, "demo_mode": False}


@app.get("/api/jw/courses")
def get_courses(
    semester_id: str = Query(..., description="学期 ID"),
    start_date: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    sess: UserSession = Depends(require_session),
) -> dict[str, Any]:
    now = utc_plus_8().date()
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)
    s_date = (start_date or "").strip() or monday.isoformat()
    e_date = (end_date or "").strip() or sunday.isoformat()

    if sess.demo_mode:
        return {
            "semester_id": semester_id,
            "start_date": s_date,
            "end_date": e_date,
            "data": demo_data.get_demo_course_table(s_date),
            "demo_mode": True,
        }

    data = ZZUClient(sess).get_course_table(
        semester_id=semester_id,
        start_date=s_date,
        end_date=e_date,
    )
    return {
        "semester_id": semester_id,
        "start_date": s_date,
        "end_date": e_date,
        "data": data,
        "demo_mode": False,
    }


@app.get("/api/jw/grades")
def get_grades(
    kind: str = Query("all", description="成绩类型，默认 all"),
    sess: UserSession = Depends(require_session),
) -> dict[str, Any]:
    if sess.demo_mode:
        return {"data": demo_data.get_demo_grades(), "demo_mode": True}
    data = ZZUClient(sess).get_grades(kind=kind)
    return {"data": data, "demo_mode": False}


@app.get("/api/jw/exams")
def get_exams(
    semester_id: str = Query(..., description="学期 ID"),
    sess: UserSession = Depends(require_session),
) -> dict[str, Any]:
    if sess.demo_mode:
        return {"data": demo_data.get_demo_exams(), "demo_mode": True}
    data = ZZUClient(sess).get_exam_tasks(semester_id=semester_id)
    return {"data": data, "demo_mode": False}


# ------------------------------------------------------------------
# E-Card Routes (校园卡 / 宿舍电费 / 卡对卡转账)
# ------------------------------------------------------------------
@app.get("/api/ecard/summary")
def get_ecard_summary(
    refresh: bool = Query(False, description="是否强制刷新校园卡 Token"),
    sess: UserSession = Depends(require_session),
) -> dict[str, Any]:
    if sess.demo_mode:
        return {"data": demo_data.get_demo_ecard_details(sess), "demo_mode": True}

    client = ZZUClient(sess)
    if refresh:
        client.ensure_ecard_token(force_refresh=True)
    details = client.get_account_details()
    return {"data": details, "demo_mode": False}


@app.post("/api/ecard/transfer")
def transfer_c2c(
    payload: TransferRequest,
    sess: UserSession = Depends(require_session),
) -> dict[str, Any]:
    from_id = payload.from_id.strip() or sess.account
    to_id = payload.to_id.strip()

    if from_id == to_id:
        raise HTTPException(status_code=400, detail="付款学号与收款学号不能相同")

    if sess.demo_mode:
        if payload.amount > sess.demo_card_balance:
            raise HTTPException(status_code=400, detail="演示模式：校园卡余额不足")
        sess.demo_card_balance = round(sess.demo_card_balance - payload.amount, 2)
        record = {
            "from_id": from_id,
            "to_id": to_id,
            "amount": payload.amount,
            "time": utc_plus_8().strftime("%Y-%m-%d %H:%M:%S"),
        }
        sess.demo_transfers.insert(0, record)
        return {
            "success": True,
            "message": f"演示模式：已模拟向 {to_id} 转账 {payload.amount:.2f} 元",
            "new_balance": f"{sess.demo_card_balance:.2f}",
            "demo_mode": True,
        }

    # Upstream API accepts int or numeric amount
    amount_val: int | float = int(payload.amount) if float(payload.amount).is_integer() else round(payload.amount, 2)
    result = ZZUClient(sess).c2c_transaction(
        from_id=from_id,
        to_id=to_id,
        amount=amount_val,
        card_password=payload.card_password,
    )
    return {**result, "demo_mode": False}


# ------------------------------------------------------------------
# Static SPA Hosting
# ------------------------------------------------------------------
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
