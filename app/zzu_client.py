"""Refactored multi-user ZZU Mobile Campus API client.

Based on TorCroft/ZZU-API (https://github.com/TorCroft/ZZU-API), adapted for
stateless/multi-user web deployments with automatic token refresh, timeouts,
and proxy support.
"""

from __future__ import annotations

import json
import time
from base64 import b64decode
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from .config import settings
from .session import UserSession

REQUIRED_DORM_PARAMS = ["building", "area", "level", "room"]
ECARD_TOKEN_REFRESH_INTERVAL = 3000  # upstream ECardAccessToken lasts 3600s


class ZZUApiError(Exception):
    def __init__(self, message: str = "ZZU API request failed", status_code: int = 502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ZZULoginError(ZZUApiError):
    def __init__(self, message: str = "登录失败，请检查学号或密码"):
        super().__init__(message, status_code=401)


class ZZUTokenError(ZZUApiError):
    def __init__(self, message: str = "令牌已过期或无效，请重新登录"):
        super().__init__(message, status_code=401)


class ZZUMFARequiredError(ZZUApiError):
    def __init__(
        self,
        message: str = "郑州大学认证中心要求进行二次验证（MFA）",
        mfa_state: str = "",
        mfa_data: dict[str, Any] | None = None,
    ):
        super().__init__(message, status_code=428)
        self.mfa_state = mfa_state
        self.mfa_data = mfa_data or {}


def utc_plus_8() -> datetime:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))


def timestamp_13_digit() -> int:
    return int(utc_plus_8().timestamp() * 1000)


def get_today_date_str() -> str:
    return utc_plus_8().strftime("%Y-%m-%d")


def decode_business_data(data: Any) -> Any:
    if data is None or data == "":
        return None
    if isinstance(data, (dict, list)):
        return data
    if isinstance(data, str):
        try:
            decoded = b64decode(data.encode("utf-8")).decode("utf-8")
            return json.loads(decoded)
        except Exception:
            try:
                return json.loads(data)
            except Exception:
                return data
    return data


def find_available_classroom(
    rooms: list[dict[str, Any]],
    floor: str | None = None,
    periods: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Filter classrooms by optional floor and required free periods (1~10).

    In ZZU occupancy data, each room has `occupy_units` where '0' = available
    and '1' = occupied.
    """
    target_periods = [p for p in (periods or []) if 1 <= p <= 12]
    matched: list[dict[str, Any]] = []

    for classroom in rooms:
        room_floor = classroom.get("floor")
        if floor is not None and str(floor).strip() != "":
            try:
                if int(room_floor) != int(floor):
                    continue
            except (TypeError, ValueError):
                if str(room_floor) != str(floor):
                    continue

        occupy_units = str(classroom.get("occupy_units") or "")
        is_available = True
        for period in target_periods:
            idx = period - 1
            if idx < len(occupy_units) and occupy_units[idx] == "1":
                is_available = False
                break

        if is_available:
            matched.append(classroom)

    return matched


class ZZUClient:
    TOKEN_HOST = "https://token.s.zzu.edu.cn"
    ECARD_HOST = "https://ecard.v.zzu.edu.cn"
    JW_HOST = "https://jw.v.zzu.edu.cn"

    def __init__(self, session: UserSession | None = None) -> None:
        self.session = session

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", settings.request_timeout)
        if settings.proxies:
            kwargs.setdefault("proxies", settings.proxies)
        try:
            return requests.request(method, url, **kwargs)
        except requests.Timeout as exc:
            raise ZZUApiError(
                "连接郑州大学服务器超时，可能是校外网络波动或 Render 机房访问受限。",
                status_code=504,
            ) from exc
        except requests.RequestException as exc:
            raise ZZUApiError(
                f"无法连接到郑州大学服务器：{exc}",
                status_code=502,
            ) from exc

    @staticmethod
    def _parse_json(resp: requests.Response) -> dict[str, Any]:
        try:
            data = resp.json()
        except ValueError as exc:
            raise ZZUApiError(
                f"上游接口返回非 JSON 内容 (HTTP {resp.status_code})",
                status_code=502,
            ) from exc
        if not isinstance(data, dict):
            raise ZZUApiError("上游接口返回格式异常", status_code=502)
        return data

    # ------------------------------------------------------------------
    # Unified Authentication (with Supwisdom MFA detection & verification)
    # ------------------------------------------------------------------
    APP_ID = "com.lantu.MobileCampus.zzu"
    CLIENT_ID = "477e40a75443827bf1e1fc9eee94f561"
    DEFAULT_DEVICE_ID = "79C26735-C663-4708-9C69-8108E2E9ECD8"

    def _token_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/x-www-form-urlencoded",
            "Connection": "keep-alive",
            "X-Device-Infos": f"packagename={self.APP_ID};version=2.3.2;system=iOS",
            "Accept": "application/json",
            "User-Agent": "SWSuperApp/2.3.2 (iPhone; iOS 17.0.2; Scale/3.00)",
            "Accept-Language": "zh-CN",
            "Accept-Encoding": "gzip, deflate, br",
        }

    def detect_mfa(
        self,
        username: str,
        password: str,
        device_id: str | None = None,
    ) -> dict[str, Any]:
        """Call Supwisdom /mfa/detect before /password/passwordLogin to obtain mfaState."""
        dev_id = (device_id or "").strip() or self.DEFAULT_DEVICE_ID
        body = {
            "appId": self.APP_ID,
            "clientId": self.CLIENT_ID,
            "deviceId": dev_id,
            "osType": "iOS",
            "password": password,
            "username": username,
        }
        headers = self._token_headers()

        # Try standard POST /mfa/detect first
        resp = self._request(
            "POST",
            self.TOKEN_HOST + "/mfa/detect",
            headers=headers,
            data=body,
        )
        if resp.status_code == 404 or resp.status_code == 405:
            resp = self._request(
                "GET",
                self.TOKEN_HOST + "/mfa/detect",
                headers=headers,
                params={
                    "username": username,
                    "deviceId": dev_id,
                    "appId": self.APP_ID,
                },
            )

        payload = self._parse_json(resp)
        if int(payload.get("code", -1)) != 0:
            raise ZZULoginError(payload.get("message") or "MFA 检测失败，请检查学号或密码")

        data = payload.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        return {
            "need": bool(data.get("need", False)),
            "state": str(data.get("state") or data.get("mfaState") or ""),
            "raw": data,
        }

    def init_mfa_sms(self, mfa_state: str, mfa_type: str = "securephone") -> dict[str, Any]:
        """Initialize MFA challenge (e.g., securephone SMS) and attempt to dispatch OTP."""
        headers = self._token_headers()
        init_resp = self._request(
            "GET",
            f"{self.TOKEN_HOST}/mfa/initByType/{mfa_type}",
            headers=headers,
            params={"state": mfa_state},
        )
        init_payload = self._parse_json(init_resp)
        if int(init_payload.get("code", -1)) != 0:
            raise ZZUApiError(
                init_payload.get("message") or "初始化二次验证失败",
                status_code=400,
            )

        data = init_payload.get("data") or {}
        gid = ""
        if isinstance(data, dict):
            gid = str(data.get("gid") or data.get("id") or "")

        # Attempt to trigger SMS sending if gid is present
        send_result: dict[str, Any] = {}
        if gid:
            for send_url in (
                f"{self.TOKEN_HOST}/mfa/send",
                f"{self.TOKEN_HOST}/attest/api/guard/{mfa_type}/send",
            ):
                try:
                    s_resp = self._request(
                        "POST",
                        send_url,
                        headers=headers,
                        data={"gid": gid, "state": mfa_state},
                    )
                    if s_resp.status_code < 400:
                        send_result = self._parse_json(s_resp)
                        break
                except ZZUApiError:
                    continue

        return {
            "gid": gid,
            "state": mfa_state,
            "init_data": data,
            "send_result": send_result,
        }

    def verify_mfa_code(
        self,
        mfa_state: str,
        code: str,
        gid: str = "",
        mfa_type: str = "securephone",
    ) -> dict[str, Any]:
        """Verify SMS/OTP code for Supwisdom MFA."""
        headers = self._token_headers()
        last_err = "验证码校验失败"
        for verify_url in (
            f"{self.TOKEN_HOST}/mfa/valid",
            f"{self.TOKEN_HOST}/mfa/verify",
            f"{self.TOKEN_HOST}/attest/api/guard/{mfa_type}/valid",
        ):
            try:
                resp = self._request(
                    "POST",
                    verify_url,
                    headers=headers,
                    data={
                        "gid": gid,
                        "state": mfa_state,
                        "code": code.strip(),
                    },
                )
                if resp.status_code >= 400:
                    continue
                payload = self._parse_json(resp)
                if int(payload.get("code", -1)) == 0 or payload.get("success"):
                    return payload
                last_err = payload.get("message") or last_err
            except ZZUApiError as exc:
                last_err = exc.message
        raise ZZULoginError(last_err)

    def login(
        self,
        username: str,
        password: str,
        mfa_state: str = "",
        device_id: str | None = None,
    ) -> str:
        dev_id = (device_id or "").strip() or self.DEFAULT_DEVICE_ID
        resolved_mfa_state = mfa_state.strip()
        detect_info: dict[str, Any] = {}

        # Step 1: If caller did not already provide a verified mfa_state, run /mfa/detect
        if not resolved_mfa_state:
            try:
                detect_info = self.detect_mfa(username, password, device_id=dev_id)
                resolved_mfa_state = detect_info.get("state", "")
                if detect_info.get("need"):
                    raise ZZUMFARequiredError(
                        message="郑州大学认证检测到新设备/异地登录，需要完成短信二次验证（或改用 UserToken 登录）。",
                        mfa_state=resolved_mfa_state,
                        mfa_data=detect_info.get("raw") or {},
                    )
            except ZZUMFARequiredError:
                raise
            except ZZUApiError:
                # If /mfa/detect itself fails unexpectedly, still attempt passwordLogin below
                # so upstream returns the authoritative error.
                pass

        # Step 2: /password/passwordLogin with resolved mfaState
        path = "/password/passwordLogin"
        body = {
            "appId": self.APP_ID,
            "clientId": self.CLIENT_ID,
            "deviceId": dev_id,
            "mfaState": resolved_mfa_state,
            "osType": "iOS",
            "password": password,
            "username": username,
        }
        resp = self._request(
            "POST",
            self.TOKEN_HOST + path,
            headers=self._token_headers(),
            data=body,
        )
        payload = self._parse_json(resp)
        if int(payload.get("code", -1)) != 0:
            msg = str(payload.get("message") or "学号或密码错误")
            if "mfa" in msg.lower():
                raise ZZUMFARequiredError(
                    message=(
                        f"上游返回 {msg}：郑州大学认证中心拦截了无二次验证的登录请求。"
                        "请尝试短信二次验证，或在「UserToken 登录」页粘贴移动校园 idToken 登录。"
                    ),
                    mfa_state=resolved_mfa_state,
                    mfa_data={"upstream_message": msg, "detect": detect_info},
                )
            raise ZZULoginError(msg)

        id_token = (payload.get("data") or {}).get("idToken")
        if not id_token:
            raise ZZULoginError("登录成功但未返回 UserToken")

        if self.session is not None:
            self.session.user_token = id_token
        return id_token

    # ------------------------------------------------------------------
    # E-Card (校园卡 / 宿舍电费 / 卡对卡转账)
    # ------------------------------------------------------------------
    def _ecard_headers(self, include_auth: bool = True) -> dict[str, str]:
        assert self.session is not None
        return {
            "Accept": "*/*",
            "Authorization": self.session.ecard_access_token if include_auth else "",
            "Sec-Fetch-Site": "same-origin",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Mode": "cors",
            "Content-Type": "application/json",
            "Origin": self.ECARD_HOST,
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Html5Plus/1.0 (Immersed/47) uni-app SuperApp-10459",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Cookie": f"JSESSIONID={self.session.jsession_id}; userToken={self.session.user_token}",
        }

    def get_jid_and_tid(self) -> tuple[str, str]:
        assert self.session is not None
        if not self.session.user_token:
            raise ZZUTokenError("缺少 UserToken，请先登录")

        path = "/server/auth/host/open"
        query_params = {
            "host": "11",
            "org": "2",
            "X-Id-Token": self.session.user_token,
        }
        headers = {
            "Sec-Fetch-Site": "none",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Mode": "navigate",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Html5Plus/1.0 (Immersed/47) uni-app SuperApp-10459",
            "X-Id-Token": self.session.user_token,
            "Sec-Fetch-Dest": "document",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        resp = self._request(
            "GET",
            self.ECARD_HOST + path,
            params=query_params,
            headers=headers,
            allow_redirects=False,
        )

        target_resp = resp.history[0] if resp.history else resp
        jsession_id = target_resp.cookies.get("JSESSIONID") or ""
        location = target_resp.headers.get("Location") or ""

        tid = ""
        if location:
            parsed = urlparse(location)
            tid_list = parse_qs(parsed.query).get("tid")
            if tid_list:
                tid = tid_list[0]
            elif "?tid=" in location:
                tid = location.split("?tid=", 1)[1].split("&", 1)[0]

        if not jsession_id or not tid:
            raise ZZUTokenError("获取校园卡会话凭证 (JSESSIONID/tid) 失败，请重新登录")

        self.session.jsession_id = jsession_id
        self.session.tid = tid
        return jsession_id, tid

    def get_ecard_token(self) -> tuple[str, str]:
        assert self.session is not None
        path = "/server/auth/getToken"
        resp = self._request(
            "POST",
            self.ECARD_HOST + path,
            headers=self._ecard_headers(include_auth=False),
            json={"tid": self.session.tid},
        )
        payload = self._parse_json(resp)
        if not payload.get("success"):
            raise ZZULoginError(payload.get("message") or "获取校园卡令牌失败")

        result_data = payload.get("resultData") or {}
        self.session.refresh_token = result_data.get("refreshToken", "")
        self.session.ecard_access_token = result_data.get("accessToken", "")
        self.session.ecard_token_updated_at = time.time()
        return self.session.ecard_access_token, self.session.refresh_token

    def refresh_access_token(self) -> tuple[str, str]:
        assert self.session is not None
        path = "/server/auth/updateToken"
        resp = self._request(
            "POST",
            self.ECARD_HOST + path,
            headers=self._ecard_headers(include_auth=True),
            json={"refreshToken": self.session.refresh_token},
        )
        payload = self._parse_json(resp)
        if not payload.get("success"):
            raise ZZUApiError(payload.get("message") or "刷新校园卡令牌失败", status_code=401)

        result_data = payload.get("resultData") or {}
        self.session.refresh_token = result_data.get("refreshToken", "")
        self.session.ecard_access_token = result_data.get("accessToken", "")
        self.session.ecard_token_updated_at = time.time()
        return self.session.ecard_access_token, self.session.refresh_token

    def ensure_ecard_token(self, force_refresh: bool = False) -> None:
        assert self.session is not None
        now = time.time()
        token_expired = (
            not self.session.ecard_access_token
            or (now - self.session.ecard_token_updated_at) > ECARD_TOKEN_REFRESH_INTERVAL
        )
        if not force_refresh and not token_expired:
            return

        if self.session.refresh_token and self.session.jsession_id:
            try:
                self.refresh_access_token()
                return
            except ZZUApiError:
                pass

        self.get_jid_and_tid()
        self.get_ecard_token()

    def _ecard_post(self, path: str, body: dict[str, Any], retry: bool = True) -> dict[str, Any]:
        self.ensure_ecard_token()
        resp = self._request(
            "POST",
            self.ECARD_HOST + path,
            headers=self._ecard_headers(include_auth=True),
            json=body,
        )
        payload = self._parse_json(resp)
        if not payload.get("success"):
            if retry:
                self.ensure_ecard_token(force_refresh=True)
                return self._ecard_post(path, body, retry=False)
            raise ZZUApiError(payload.get("message") or "校园卡接口调用失败", status_code=400)
        return payload

    def get_dorm_location_dict(self) -> dict[str, Any]:
        payload = self._ecard_post("/server/utilities/config", {"utilityType": "electric"})
        location = (payload.get("resultData") or {}).get("location") or {}
        result: dict[str, Any] = {}
        for param in REQUIRED_DORM_PARAMS:
            result[param] = location.get(param, "")
        result["utilityType"] = "electric"
        return result

    def get_account_details(self) -> dict[str, Any]:
        location = self.get_dorm_location_dict()
        payload = self._ecard_post("/server/utilities/account", location)
        details = payload.get("resultData") or {}
        template_list = details.get("templateList") or []

        card_balance = None
        electric_balance = None
        electric_unit = "度"

        if len(template_list) > 0 and isinstance(template_list[0], dict):
            card_balance = template_list[0].get("value")
        if len(template_list) > 3 and isinstance(template_list[3], dict):
            electric_balance = template_list[3].get("value")
            electric_unit = template_list[3].get("unit") or electric_unit

        return {
            "utilityAccount": details.get("utilityAccount") or (self.session.account if self.session else ""),
            "utilityUsername": details.get("utilityUsername") or "",
            "card_balance": card_balance,
            "electric_balance": electric_balance,
            "electric_unit": electric_unit,
            "location": location,
            "templateList": template_list,
            "raw": details,
        }

    def c2c_transaction(
        self,
        from_id: str,
        to_id: str,
        amount: float | int,
        card_password: str,
    ) -> dict[str, Any]:
        body = {
            "fromIdSerial": str(from_id).strip(),
            "toIdSerial": str(to_id).strip(),
            "txAmt": amount,
            "password": str(card_password),
        }
        payload = self._ecard_post(
            "/server/c2cTransaction/transferFromCard2Card",
            body,
            retry=False,  # Never auto-retry money transfer!
        )
        return {
            "success": True,
            "message": payload.get("message") or f"已向 {to_id} 转账 {amount} 元",
            "resultData": payload.get("resultData"),
        }

    # ------------------------------------------------------------------
    # JW Academic System (教务系统：空教室 / 学期 / 课表 / 作息 / 成绩 / 考试)
    # ------------------------------------------------------------------
    def _jw_headers(self, include_token: bool = True, cookie: str = "SVRNAME=ws1") -> dict[str, str]:
        assert self.session is not None
        headers = {
            "Host": "jw.v.zzu.edu.cn",
            "Accept": "application/json, text/plain, */*",
            "Sec-Fetch-Site": "same-origin",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Mode": "cors",
            "Origin": self.JW_HOST,
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 SuperApp SuperApp-10459",
            "Referer": "https://jw.v.zzu.edu.cn/app-web/",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "Sec-Fetch-Dest": "empty",
            "Cookie": cookie,
        }
        if include_token and self.session.jw_token:
            headers["token"] = self.session.jw_token
        return headers

    def get_jw_token(self) -> str:
        assert self.session is not None
        if not self.session.user_token:
            raise ZZUTokenError("缺少 UserToken，请先登录")

        path = "/app-ws/ws/app-service/super/app/login-token"
        data = {
            "userToken": self.session.user_token,
            "timestamp": timestamp_13_digit(),
        }
        resp = self._request(
            "POST",
            self.JW_HOST + path,
            headers=self._jw_headers(include_token=False, cookie="SVRNAME=web1"),
            data=data,
        )
        payload = self._parse_json(resp)
        if int(payload.get("err_code", -1)) != 0:
            raise ZZUTokenError(payload.get("err_msg") or "获取教务系统令牌失败")

        decoded = decode_business_data(payload.get("business_data"))
        if not isinstance(decoded, dict) or not decoded.get("token"):
            raise ZZUTokenError("教务系统未返回有效 token")

        self.session.jw_token = decoded["token"]
        return self.session.jw_token

    def _jw_post(self, path: str, extra_data: dict[str, Any], retry: bool = True) -> Any:
        assert self.session is not None
        if not self.session.jw_token:
            self.get_jw_token()

        form_data = {
            **extra_data,
            "timestamp": timestamp_13_digit(),
            "token": self.session.jw_token,
        }
        resp = self._request(
            "POST",
            self.JW_HOST + path,
            headers=self._jw_headers(include_token=True),
            data=form_data,
        )
        payload = self._parse_json(resp)
        if int(payload.get("err_code", -1)) != 0:
            if retry:
                self.get_jw_token()
                return self._jw_post(path, extra_data, retry=False)
            raise ZZUTokenError(payload.get("err_msg") or "教务系统接口返回错误")

        return decode_business_data(payload.get("business_data"))

    def get_campus_building(self) -> Any:
        return self._jw_post(
            "/app-ws/ws/app-service/room/borrow/campus/building/search",
            {"authorized": "true"},
        )

    def get_room_data_by_building_id(
        self,
        building_id: int | str,
        date_str: str | None = None,
    ) -> Any:
        target_date = date_str or get_today_date_str()
        return self._jw_post(
            "/app-ws/ws/app-service/room/borrow/occupancy/search",
            {
                "building_id": str(building_id),
                "start_date": target_date,
                "end_date": None,
            },
        )

    def get_semester(self, biz_type_id: str = "1") -> Any:
        return self._jw_post(
            "/app-ws/ws/app-service/common/get-semester",
            {"biz_type_id": biz_type_id},
        )

    def get_course_table(
        self,
        semester_id: int | str,
        start_date: str,
        end_date: str,
        biz_type_id: str = "1",
    ) -> Any:
        return self._jw_post(
            "/app-ws/ws/app-service/student/course/schedule/get-course-tables",
            {
                "biz_type_id": biz_type_id,
                "semester_id": str(semester_id),
                "start_date": start_date,
                "end_date": end_date,
            },
        )

    def get_time_table(
        self,
        semester_id: int | str,
        campus_id: str = "2",
        biz_type_id: str = "1",
    ) -> Any:
        return self._jw_post(
            "/app-ws/ws/app-service/time/setting/course-unit",
            {
                "biz_type_id": biz_type_id,
                "campus_id": str(campus_id),
                "semester_id": str(semester_id),
            },
        )

    def get_grades(self, kind: str = "all", biz_type_id: str = "1") -> Any:
        return self._jw_post(
            "/app-ws/ws/app-service/student/exam/grade/get-grades",
            {
                "biz_type_id": biz_type_id,
                "kind": kind,
            },
        )

    def get_exam_tasks(self, semester_id: int | str, biz_type_id: str = "1") -> Any:
        return self._jw_post(
            "/app-ws/ws/app-service/student/exam/schedule/lesson/get-exam-tasks",
            {
                "biz_type_id": biz_type_id,
                "semester_id": str(semester_id),
            },
        )
