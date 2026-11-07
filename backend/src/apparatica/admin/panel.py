"""The admin panel `/admin` (FR-ADM-02, its phase 3 part): SQLAdmin for moderators and
administrators — users, public solutions and the journal of moderation.

- Access: the session of the site (ADR-0010), checked by `StaffOnly` for every request of the
  panel, its static files included. Without a session the panel sends to the login page and back;
  a signed-in user without the role gets 403. A role is read at each request.
- SQLAdmin itself only reads: no create, edit, delete or export. A change goes through the
  moderation page of a view (`/admin/<view>/moderate`): a form with the required reason, sent by
  POST, which the CSRF middleware lets through only from the origin of the site. The action
  buttons of SQLAdmin are GET requests and only lead to that page.
- Who may do what (`StaffPermissions`): a moderator and an administrator hide and show; only an
  administrator gives roles (`apparatica.admin.moderation`).
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, cast, get_args
from urllib.parse import quote

from fastapi import FastAPI
from markupsafe import Markup
from sqladmin import Admin, ModelView, action, expose
from sqladmin.authorization import Action, AuthorizationBackend, custom_action
from sqladmin.filters import BooleanFilter, StaticValuesFilter
from sqladmin.i18n import I18nConfig
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from apparatica.admin.models import ModerationLog
from apparatica.admin.moderation import (
    STAFF,
    Moderation,
    ModerationRefusedError,
    Refusal,
    Staff,
)
from apparatica.auth.models import User
from apparatica.auth.schemas import Role
from apparatica.auth.sessions import COOKIE, Sessions
from apparatica.core.db import Database
from apparatica.core.platform import RatingFormula
from apparatica.submissions.models import Submission

BASE_URL = "/admin"
TEMPLATES = Path(__file__).parent / "templates"
REASON_MAX_LENGTH = 1000

ROLE_TITLES: dict[str, str] = {
    "user": "пользователь",
    "author": "автор задач",
    "moderator": "модератор",
    "admin": "администратор",
}
ACTION_TITLES = {"hide": "скрытие", "unhide": "снятие скрытия", "set_role": "смена роли"}
REFUSALS: dict[Refusal, str] = {
    "staff_target": "Модератора и администратора скрыть нельзя: сначала снимите роль.",
    "own_role": "Свою роль менять нельзя.",
    "not_admin": "Роли выдаёт только администратор.",
    "hidden_staff": "Скрытому пользователю нельзя дать роль модератора или администратора.",
}


class FormError(Exception):
    """A form the panel cannot apply; the message is shown to the moderator."""


class StaffOnly:
    """Lets moderators and administrators in (pure ASGI): `request.state.staff` is who acts."""

    def __init__(self, app: ASGIApp, *, sessions: Sessions, database: Database) -> None:
        self.app = app
        self.sessions = sessions
        self.database = database

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        token = request.cookies.get(COOKIE)
        found = await self.sessions.find(token) if token is not None else None
        staff = None
        if found is not None:
            async with self.database.sessions() as session:
                user = await session.get(User, found.user_id)
            if user is not None and user.role in STAFF:
                staff = Staff(user.id, user.nick, user.role)  # narrowed by STAFF
        response: Response | None = None
        if found is None:
            back = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            response = RedirectResponse(f"/login?next={quote(back, safe='/')}", 303)
        elif staff is None:
            response = PlainTextResponse(
                "Админка доступна только модераторам и администраторам.", 403
            )
        if response is not None:
            await response(scope, receive, send)
            return
        scope.setdefault("state", {})["staff"] = staff
        await self.app(scope, receive, send)


def staff_of(request: Request) -> Staff:
    staff: Staff = request.state.staff
    return staff


class StaffPermissions(AuthorizationBackend):
    """Both roles read everything and hide or show; only an administrator gives roles."""

    def has_permission(
        self, request: Request, identity: str, action: str, obj: Any | None = None
    ) -> bool:
        if action in (Action.LIST, Action.DETAILS):
            return True
        if action in (custom_action("hide"), custom_action("unhide")):
            return identity in ("user", "submission")
        if action == custom_action("role"):
            return identity == "user" and staff_of(request).role == "admin"
        return False


class Panel(Admin):
    moderation: Moderation


class _Moderated(ModelView):
    """A read-only view whose rows a moderator hides and shows through the moderation page."""

    can_create = False
    can_edit = False
    can_delete = False
    can_export = False
    page_size = 50
    page_size_options: ClassVar[list[int]] = [50, 100]

    @action("hide", "Скрыть")
    async def hide(self, request: Request) -> Response:
        return self._to_form(request, "hide")

    @action("unhide", "Снять скрытие")
    async def unhide(self, request: Request) -> Response:
        return self._to_form(request, "unhide")

    def _to_form(self, request: Request, kind: str) -> Response:
        url = request.url_for(f"admin:view-{self.identity}-moderate").include_query_params(
            action=kind, pks=request.query_params.get("pks", "")
        )
        return RedirectResponse(str(url), 303)

    @expose("/moderate", methods=["GET", "POST"])
    async def moderate(self, request: Request) -> Response:
        """The form of an action with its reason; POST applies it."""
        source = await request.form() if request.method == "POST" else request.query_params
        kind = str(source.get("action", ""))
        ids = _ids(str(source.get("pks", "")))
        if kind not in self._actions(request) or not ids:
            return PlainTextResponse("Не выбраны действие или строки.", 400)
        if kind == "role" and len(ids) != 1:
            return PlainTextResponse("Роль меняется у одного пользователя за раз.", 400)
        targets = await self.targets(ids)
        if not targets:
            return PlainTextResponse("Строки не найдены.", 404)
        context: dict[str, Any] = {
            "title": self.name_plural,
            "subtitle": "Модерация",
            "view": self,
            "kind": kind,
            "action_title": self._action_title(kind),
            "pks": ",".join(str(target_id) for target_id, _, _ in targets),
            "targets": targets,
            "roles": ROLE_TITLES,
            "back": str(request.url_for("admin:list", identity=self.identity)),
            "reason": "",
            "error": None,
        }
        if request.method == "POST":
            reason = str(source.get("reason", "")).strip()
            context["reason"] = reason
            if not reason:
                context["error"] = "Укажите причину: она попадёт в журнал модерации."
            elif len(reason) > REASON_MAX_LENGTH:
                context["error"] = f"Причина длиннее {REASON_MAX_LENGTH} символов."
            else:
                chosen = [target_id for target_id, _, _ in targets]
                try:
                    await self.apply(request, kind, chosen, reason, source)
                except ModerationRefusedError as refused:
                    context["error"] = REFUSALS[refused.refusal]
                except FormError as error:
                    context["error"] = str(error)
                else:
                    return RedirectResponse(self._after(request, targets), 303)
        status = 400 if context["error"] else 200
        return await self.templates.TemplateResponse(
            request, "moderate.html", context, status_code=status
        )

    def _actions(self, request: Request) -> list[str]:
        return [
            kind for kind in ("hide", "unhide") if self.has_permission(request, custom_action(kind))
        ]

    def _action_title(self, kind: str) -> str:
        return {"hide": "Скрыть", "unhide": "Снять скрытие"}[kind]

    def _after(self, request: Request, targets: Sequence[tuple[uuid.UUID, str, str]]) -> str:
        """Back to the row when it was one, else to the list."""
        if len(targets) == 1:
            return str(
                request.url_for("admin:details", identity=self.identity, pk=str(targets[0][0]))
            )
        return str(request.url_for("admin:list", identity=self.identity))

    async def targets(self, ids: Sequence[uuid.UUID]) -> list[tuple[uuid.UUID, str, str]]:
        """The rows of the ids that exist: id, title, state."""
        raise NotImplementedError

    async def apply(
        self, request: Request, kind: str, ids: list[uuid.UUID], reason: str, form: Any
    ) -> None:
        raise NotImplementedError

    @property
    def moderation(self) -> Moderation:
        return cast(Panel, self._admin_ref).moderation


def _ids(pks: str) -> list[uuid.UUID]:
    found = []
    for part in pks.split(","):
        try:
            found.append(uuid.UUID(part.strip()))
        except ValueError:
            continue
    return list(dict.fromkeys(found))


def _hidden(value: bool) -> str:
    return "скрыт" if value else "виден"


def _when(value: datetime | None) -> str:
    return "" if value is None else value.strftime("%Y-%m-%d %H:%M UTC")


class UserView(_Moderated, model=User):
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa-solid fa-user"
    column_list: ClassVar[Any] = [
        User.nick,
        User.display_name,
        User.role,
        User.is_hidden,
        User.created_at,
        User.delete_at,
    ]
    column_details_list: ClassVar[Any] = [
        User.id,
        User.nick,
        User.display_name,
        User.role,
        User.is_hidden,
        User.created_at,
        User.nick_changed_at,
        User.delete_at,
    ]
    column_labels: ClassVar[Any] = {
        User.id: "ID",
        User.nick: "Ник",
        User.display_name: "Имя",
        User.role: "Роль",
        User.is_hidden: "Скрыт",
        User.created_at: "Зарегистрирован",
        User.nick_changed_at: "Ник сменён",
        User.delete_at: "Удаление",
    }
    column_formatters: ClassVar[Any] = {
        User.role: lambda user, _: ROLE_TITLES[user.role],
        User.created_at: lambda user, _: _when(user.created_at),
        User.delete_at: lambda user, _: _when(user.delete_at),
    }
    column_formatters_detail: ClassVar[Any] = {
        **column_formatters,
        User.nick_changed_at: lambda user, _: _when(user.nick_changed_at),
        User.nick: lambda user, _: Markup('{} · <a href="/u/{}">профиль</a>').format(
            user.nick, quote(user.nick)
        ),
    }
    column_searchable_list: ClassVar[Any] = [User.nick, User.display_name]
    column_sortable_list: ClassVar[Any] = [User.nick, User.role, User.created_at]
    column_default_sort: ClassVar[Any] = [(User.created_at, True)]
    column_filters: ClassVar[Any] = [
        StaticValuesFilter(User.role, values=list(ROLE_TITLES.items()), title="Роль"),
        BooleanFilter(User.is_hidden, title="Скрыт"),
    ]

    @action("role", "Сменить роль")
    async def role(self, request: Request) -> Response:
        return self._to_form(request, "role")

    def _actions(self, request: Request) -> list[str]:
        roles = ["role"] if self.has_permission(request, custom_action("role")) else []
        return [*super()._actions(request), *roles]

    def _action_title(self, kind: str) -> str:
        return "Сменить роль" if kind == "role" else super()._action_title(kind)

    async def targets(self, ids: Sequence[uuid.UUID]) -> list[tuple[uuid.UUID, str, str]]:
        async with self.session_maker() as session:
            users = await session.scalars(select(User).where(User.id.in_(ids)).order_by(User.nick))
            return [
                (user.id, user.nick, f"{ROLE_TITLES[user.role]}, {_hidden(user.is_hidden)}")
                for user in users
            ]

    async def apply(
        self, request: Request, kind: str, ids: list[uuid.UUID], reason: str, form: Any
    ) -> None:
        actor = staff_of(request)
        if kind == "role":
            role = str(form.get("role", ""))
            if role not in get_args(Role):
                raise FormError("Выберите роль.")
            [user_id] = ids
            await self.moderation.set_role(actor, user_id, cast(Role, role), reason)
            return
        await self.moderation.hide_users(actor, ids, hidden=kind == "hide", reason=reason)


def _solution_title(submission: Submission) -> str:
    author = submission.author.nick if submission.author is not None else "—"
    return f"{author} · {submission.version.title} v{submission.version.version}"


class SubmissionView(_Moderated, model=Submission):
    """Public solutions: accepted Submits of signed-in users."""

    name = "Решение"
    name_plural = "Решения"
    icon = "fa-solid fa-code"
    column_list: ClassVar[Any] = [
        Submission.id,
        Submission.author,
        Submission.version,
        Submission.is_hidden,
        Submission.created_at,
    ]
    column_details_list: ClassVar[Any] = [
        Submission.id,
        Submission.author,
        Submission.version,
        Submission.status,
        Submission.toolchain_profile_id,
        Submission.ast_hash,
        Submission.is_hidden,
        Submission.created_at,
        Submission.code,
    ]
    column_labels: ClassVar[Any] = {
        Submission.id: "ID",
        Submission.author: "Автор",
        Submission.version: "Задача",
        Submission.status: "Вердикт",
        Submission.toolchain_profile_id: "Профиль тулчейна",
        Submission.ast_hash: "AST-хэш",
        Submission.is_hidden: "Скрыто",
        Submission.created_at: "Отправлено",
        Submission.code: "Код",
    }
    column_formatters: ClassVar[Any] = {
        Submission.author: lambda found, _: found.author.nick if found.author else "—",
        Submission.version: lambda found, _: f"{found.version.title} v{found.version.version}",
        Submission.created_at: lambda found, _: _when(found.created_at),
    }
    column_formatters_detail: ClassVar[Any] = {
        **column_formatters,
        Submission.id: lambda found, _: Markup('{} · <a href="/solutions/{}">страница</a>').format(
            found.id, found.id
        ),
        Submission.code: lambda found, _: Markup("<pre>{}</pre>").format(found.code),
    }
    column_searchable_list: ClassVar[Any] = ["author.nick"]
    column_sortable_list: ClassVar[Any] = [Submission.created_at]
    column_default_sort: ClassVar[Any] = [(Submission.created_at, True)]
    column_filters: ClassVar[Any] = [BooleanFilter(Submission.is_hidden, title="Скрыто")]

    def list_query(self, request: Request) -> Select[Any]:
        return select(Submission).where(Submission.is_public)

    def count_query(self, request: Request) -> Select[Any]:
        return select(func.count(Submission.id)).where(Submission.is_public)

    def details_query(self, request: Request) -> Select[Any]:
        return super().details_query(request).where(Submission.is_public)

    async def targets(self, ids: Sequence[uuid.UUID]) -> list[tuple[uuid.UUID, str, str]]:
        async with self.session_maker() as session:
            submissions = await session.scalars(
                select(Submission)
                .where(Submission.id.in_(ids), Submission.is_public)
                .options(selectinload(Submission.author), selectinload(Submission.version))
                .order_by(Submission.created_at)
            )
            return [
                (found.id, _solution_title(found), _hidden(found.is_hidden))
                for found in submissions
            ]

    async def apply(
        self, request: Request, kind: str, ids: list[uuid.UUID], reason: str, form: Any
    ) -> None:
        await self.moderation.hide_submissions(
            staff_of(request), ids, hidden=kind == "hide", reason=reason
        )


def _target_link(entry: ModerationLog, _: Any) -> Markup:
    # Relative to /admin/moderation-log/list.
    return Markup('<a href="../{}/details/{}">{}</a>').format(
        entry.target_type, entry.target_id, entry.target_id
    )


class ModerationLogView(ModelView, model=ModerationLog):
    name = "Запись журнала"
    name_plural = "Журнал модерации"
    icon = "fa-solid fa-list"
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False
    page_size = 50
    column_list: ClassVar[Any] = [
        ModerationLog.created_at,
        ModerationLog.actor,
        ModerationLog.action,
        ModerationLog.target_type,
        ModerationLog.reason,
        ModerationLog.target_id,
    ]
    column_details_list: ClassVar[Any] = [*column_list, ModerationLog.details]
    column_labels: ClassVar[Any] = {
        ModerationLog.created_at: "Когда",
        ModerationLog.actor: "Кто",
        ModerationLog.action: "Действие",
        ModerationLog.target_type: "Объект",
        ModerationLog.target_id: "ID объекта",
        ModerationLog.reason: "Причина",
        ModerationLog.details: "Подробности",
    }
    column_formatters: ClassVar[Any] = {
        ModerationLog.actor: lambda entry, _: (
            entry.actor.nick if entry.actor else "apparatica-admin / удалён"
        ),
        ModerationLog.action: lambda entry, _: ACTION_TITLES.get(entry.action, entry.action),
        ModerationLog.target_type: lambda entry, _: {
            "user": "пользователь",
            "submission": "решение",
        }.get(entry.target_type, entry.target_type),
        ModerationLog.target_id: _target_link,
        ModerationLog.created_at: lambda entry, _: _when(entry.created_at),
    }
    column_formatters_detail = column_formatters
    column_searchable_list: ClassVar[Any] = [
        ModerationLog.target_id,
        ModerationLog.reason,
        "actor.nick",
    ]
    column_sortable_list: ClassVar[Any] = [ModerationLog.created_at]
    column_default_sort: ClassVar[Any] = [(ModerationLog.created_at, True)]


def mount_admin(
    app: FastAPI, database: Database, sessions: Sessions, rating: RatingFormula
) -> Panel:
    """Mount the panel at BASE_URL."""
    panel = Panel(
        app,
        # SQLAdmin configures the maker it gets (no autoflush): one of its own.
        session_maker=async_sessionmaker(database.engine, expire_on_commit=False),
        base_url=BASE_URL,
        title="Apparatica",
        templates_dir=str(TEMPLATES),
        middlewares=[Middleware(StaffOnly, sessions=sessions, database=database)],
        authorization_backend=StaffPermissions(),
        i18n_config=I18nConfig(
            default_locale="ru", language_cookie_name=None, language_header_name=None
        ),
    )
    panel.moderation = Moderation(database, rating)
    for view in (UserView, SubmissionView, ModerationLogView):
        panel.add_view(view)
    return panel
