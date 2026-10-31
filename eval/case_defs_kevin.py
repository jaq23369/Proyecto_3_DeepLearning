"""Casos de evaluación de Kevin.

Misma mecánica que eval/case_defs_joel.py: cada caso parte de un repo base
limpio en eval/repos/<base>, aplica modificaciones controladas (como si el
código hubiera cambiado y la documentación o las skills se quedaran atrás) y
las etiquetas citan texto; build_cases.py calcula las líneas.

Familias y partición:
- library (préstamos de libros): desarrollo (dev). Se puede usar para ajustar
  prompts.
- tickets (mesa de ayuda): prueba final (test). No se mira para ajustar nada.
  Junto con la familia notes de Joel forman los 10 casos de la prueba final.

Las familias son distintas a las de Joel y todos los casos de una familia van
al mismo split. Joel revisó estas etiquetas el 31 de octubre comparando cada
caso contra su repo base (reviewed_by). lib01 se mantiene como caso limpio: sus
dos skills separan tareas distintas (código y pruebas) y no compiten.
"""

LIB_API = ".claude/skills/loans-api/SKILL.md"
LIB_TESTS = ".claude/skills/loans-tests/SKILL.md"
TK_API = ".claude/skills/tickets-api/SKILL.md"
TK_DOCS = ".claude/skills/tickets-docs/SKILL.md"

CASES = [
    # --------------------------------------------------------------- library
    {
        "id": "lib01", "reviewed_by": "joel", "split": "dev", "family": "library", "base": "library", "category": "clean",
        "description": "Repo de préstamos de libros sin modificaciones. README, código y skills coinciden.",
        "expected": [],
    },
    {
        "id": "lib02", "reviewed_by": "joel", "split": "dev", "family": "library", "base": "library", "category": "readme_code",
        "description": "La ruta del historial de un socio pasó de /members/{member}/loans a /members/{member}/history en el código y las pruebas; la tabla del README no cambió.",
        "mutations": [
            ("replace", "app/main.py", '@app.get("/members/{member}/loans")', '@app.get("/members/{member}/history")'),
            ("replace", "tests/test_loans.py", '"/members/eli/loans"', '"/members/eli/history"'),
        ],
        "expected": [
            {"type": "readme_code", "evidence": [("README.md", "| GET | `/members/{member}/loans` |"),
                                                 ("app/main.py", '@app.get("/members/{member}/history")')],
             "note": "la tabla documenta /loans y el código usa /history"},
        ],
    },
    {
        "id": "lib03", "reviewed_by": "joel", "split": "dev", "family": "library", "base": "library", "category": "readme_code",
        "description": "El máximo de préstamos activos por socio subió de 3 a 5 en la configuración; el README dice 3.",
        "mutations": [
            ("replace", "app/config.py", "MAX_LOANS = 3", "MAX_LOANS = 5"),
            ("replace", "tests/test_loans.py", "for _ in range(3):", "for _ in range(5):"),
        ],
        "expected": [
            {"type": "readme_code", "evidence": [("README.md", "at most 3 active loans"), ("app/config.py", "MAX_LOANS = 5")],
             "note": "límite numérico distinto, solo lo ve el LLM"},
        ],
    },
    {
        "id": "lib04", "reviewed_by": "joel", "split": "dev", "family": "library", "base": "library", "category": "readme_code",
        "description": "El campo del cuerpo de POST /loans pasó de member a member_id; el ejemplo del README sigue usando member.",
        "mutations": [
            ("replace", "app/models.py", "    member: str", "    member_id: str"),
            ("replace", "app/main.py", "x.member == data.member and", "x.member_id == data.member_id and"),
            ("replace", "app/main.py", "if x.member == member]", "if x.member_id == member]"),
            ("replace", "tests/test_loans.py", '{"member": member, "book_id": book_id}', '{"member_id": member, "book_id": book_id}'),
        ],
        "expected": [
            {"type": "readme_code", "evidence": [("README.md", '{"member": "ana", "book_id": 1}'), ("app/models.py", "    member_id: str")],
             "note": "el ejemplo del README usa un campo que ya no existe"},
        ],
    },
    {
        "id": "lib05", "reviewed_by": "joel", "split": "dev", "family": "library", "base": "library", "category": "skill_project",
        "description": "app/config.py se renombró a app/settings.py y el código se actualizó; la skill de la API sigue apuntando a app/config.py.",
        "mutations": [
            ("rename", "app/config.py", "app/settings.py"),
            ("replace", "app/main.py", "from app.config import FINE_PER_DAY", "from app.settings import FINE_PER_DAY"),
        ],
        "expected": [
            {"type": "skill_project", "evidence": [(LIB_API, "1. Limits such as loan days")],
             "note": "la skill manda leer los límites de un archivo que ya no existe"},
            {"type": "skill_project", "evidence": [(LIB_API, "description:")], "optional": True,
             "note": "la descripción también menciona app/config.py"},
        ],
    },
    {
        "id": "lib06", "reviewed_by": "joel", "split": "dev", "family": "library", "base": "library", "category": "skill_project",
        "description": "Cuando no quedan copias, el código ahora responde 400 en vez de 409; la skill de la API sigue pidiendo 409.",
        "mutations": [
            ("replace", "app/main.py", 'raise HTTPException(status_code=409, detail="No copies left")',
             'raise HTTPException(status_code=400, detail="No copies left")'),
            ("replace", "tests/test_loans.py", 'assert lend("carl", 2).status_code == 409', 'assert lend("carl", 2).status_code == 400'),
        ],
        "expected": [
            {"type": "skill_project", "evidence": [(LIB_API, "2. Return 409 when a book has no copies left"),
                                                   ("app/main.py", 'raise HTTPException(status_code=400, detail="No copies left")')],
             "note": "código de estado distinto al que pide la skill, solo lo ve el LLM"},
        ],
    },
    {
        "id": "lib07", "reviewed_by": "joel", "split": "dev", "family": "library", "base": "library", "category": "skill_overlap",
        "description": "Las dos skills se reescribieron con descripciones distintas en palabras pero con el mismo ámbito (cualquier cambio de comportamiento de préstamos).",
        "mutations": [
            ("replace", LIB_API,
             "description: Change loan endpoints or loan rules. Use when editing app/main.py, app/models.py or app/config.py.",
             "description: Guide for working on the library loans service. Use whenever a loan, book or member behavior has to change."),
            ("replace", LIB_TESTS,
             "description: Write or fix pytest tests for loans. Use when a test fails or a loan rule needs a test in tests/.",
             "description: Guide for checking the library loans service. Use whenever loan or member behavior is added or changes."),
        ],
        "expected": [
            {"type": "skill_overlap", "evidence": [(LIB_API, "description:"), (LIB_TESTS, "description:")],
             "note": "traslape parafraseado, las reglas no lo ven"},
        ],
    },
    {
        "id": "lib08", "reviewed_by": "joel", "split": "dev", "family": "library", "base": "library", "category": "redundancy",
        "description": "Se agregó a la skill de la API una instrucción que repite con otras palabras la de correr pytest de la skill de pruebas.",
        "mutations": [
            ("replace", LIB_API, "4. After changing a route, update the endpoint table in `README.md`.",
             "4. After changing a route, update the endpoint table in `README.md`.\n5. Before you finish, run the loan tests with pytest and report what happened."),
        ],
        "expected": [
            {"type": "redundancy", "evidence": [(LIB_API, "5. Before you finish, run the loan tests"), (LIB_TESTS, "4. Run `pytest tests/test_loans.py`")],
             "note": "misma instrucción con otras palabras"},
        ],
    },
    {
        "id": "lib09", "reviewed_by": "joel", "split": "dev", "family": "library", "base": "library", "category": "skill_format",
        "description": "A la skill de pruebas se le borró el campo description del frontmatter, que la especificación de Agent Skills exige.",
        "mutations": [
            ("replace", LIB_TESTS,
             "description: Write or fix pytest tests for loans. Use when a test fails or a loan rule needs a test in tests/.\n", ""),
        ],
        "expected": [
            {"type": "skill_format", "evidence": [(LIB_TESTS, "name: loans-tests")], "note": "frontmatter sin description"},
        ],
    },
    {
        "id": "lib10", "reviewed_by": "joel", "split": "dev", "family": "library", "base": "library", "category": "mixed",
        "description": "El plazo de préstamo subió de 14 a 21 días y la multa de 0.50 a 0.75 por día en la configuración; el README sigue con los valores viejos.",
        "mutations": [
            ("replace", "app/config.py", "LOAN_DAYS = 14", "LOAN_DAYS = 21"),
            ("replace", "app/config.py", "FINE_PER_DAY = 0.50", "FINE_PER_DAY = 0.75"),
            ("replace", "tests/test_loans.py", '== 1.0', '== 1.5'),
        ],
        "expected": [
            {"type": "readme_code", "evidence": [("README.md", "A loan lasts 14 days."), ("app/config.py", "LOAN_DAYS = 21")],
             "note": "plazo documentado distinto al del código"},
            {"type": "readme_code", "evidence": [("README.md", "costs 0.50 per day"), ("app/config.py", "FINE_PER_DAY = 0.75")],
             "note": "multa documentada distinta a la del código"},
        ],
    },
    # --------------------------------------------------------- tickets (test)
    {
        "id": "tk01", "reviewed_by": "joel", "split": "test", "family": "tickets", "base": "tickets", "category": "clean",
        "description": "Repo de mesa de ayuda sin modificaciones.",
        "expected": [],
    },
    {
        "id": "tk02", "reviewed_by": "joel", "split": "test", "family": "tickets", "base": "tickets", "category": "mixed",
        "description": "Cerrar un ticket pasó de /close a /resolve y la prioridad normal se renombró a medium; el README quedó con los dos valores viejos.",
        "mutations": [
            ("replace", "helpdesk/routes.py", '@router.post("/{ticket_id}/close")', '@router.post("/{ticket_id}/resolve")'),
            ("replace_all", "tests/test_tickets.py", "/close", "/resolve"),
            ("replace", "helpdesk/config.py", 'PRIORITIES = ("low", "normal", "high")', 'PRIORITIES = ("low", "medium", "high")'),
            ("replace", "helpdesk/schemas.py", 'priority: str = "normal"', 'priority: str = "medium"'),
            ("replace", "tests/test_tickets.py", 'priority: str = "normal"', 'priority: str = "medium"'),
        ],
        "expected": [
            {"type": "readme_code", "evidence": [("README.md", "`POST /api/tickets/{ticket_id}/close`"),
                                                 ("helpdesk/routes.py", '@router.post("/{ticket_id}/resolve")')],
             "note": "ruta de cierre desactualizada en el README"},
            {"type": "readme_code", "evidence": [("README.md", "to `low`, `normal` or `high`"),
                                                 ("helpdesk/config.py", 'PRIORITIES = ("low", "medium", "high")')],
             "note": "la prioridad normal ya no existe, solo lo ve el LLM"},
        ],
    },
    {
        "id": "tk03", "reviewed_by": "joel", "split": "test", "family": "tickets", "base": "tickets", "category": "readme_code",
        "description": "La variable de entorno del límite de título pasó de HELPDESK_MAX_TITLE a HELPDESK_TITLE_LIMIT; el README sigue con el nombre viejo.",
        "mutations": [
            ("replace", "helpdesk/config.py", 'os.getenv("HELPDESK_MAX_TITLE", "80")', 'os.getenv("HELPDESK_TITLE_LIMIT", "80")'),
        ],
        "expected": [
            {"type": "readme_code", "evidence": [("README.md", "Set `HELPDESK_MAX_TITLE`"),
                                                 ("helpdesk/config.py", 'os.getenv("HELPDESK_TITLE_LIMIT", "80")')],
             "note": "el nombre de la variable de entorno cambió"},
        ],
    },
    {
        "id": "tk04", "reviewed_by": "joel", "split": "test", "family": "tickets", "base": "tickets", "category": "mixed",
        "description": "La skill de documentación copió la condición de uso de la skill de la API (con otras palabras) y una de sus instrucciones.",
        "mutations": [
            ("replace", TK_DOCS,
             "description: Keep the README in sync with the code. Use when the user asks to update or review the documentation.",
             "description: Help with the helpdesk tickets service. Use whenever a ticket route is added, changed or removed."),
            ("replace", TK_DOCS, "3. Write short sentences in English.",
             "3. Write short sentences in English.\n4. Remember that closing a ticket only marks it as closed; never delete it."),
        ],
        "expected": [
            {"type": "skill_overlap", "evidence": [(TK_API, "description:"), (TK_DOCS, "description:")],
             "note": "misma condición de uso con otras palabras"},
            {"type": "redundancy", "evidence": [(TK_API, "3. Closing a ticket sets its status"), (TK_DOCS, "4. Remember that closing a ticket")],
             "note": "misma instrucción con otras palabras"},
        ],
    },
    {
        "id": "tk05", "reviewed_by": "joel", "split": "test", "family": "tickets", "base": "tickets", "category": "mixed",
        "description": "El archivo de pruebas se renombró a tests/test_helpdesk.py y el filtro de la lista pasó de status a state; README y skill siguen con lo viejo.",
        "mutations": [
            ("rename", "tests/test_tickets.py", "tests/test_helpdesk.py"),
            ("replace", "helpdesk/routes.py", "def list_tickets(status: str | None = None)", "def list_tickets(state: str | None = None)"),
            ("replace", "helpdesk/routes.py", "if status is None or t.status == status]", "if state is None or t.status == state]"),
            ("replace", "tests/test_helpdesk.py", 'params={"status": "open"}', 'params={"state": "open"}'),
        ],
        "expected": [
            {"type": "readme_code", "evidence": [("README.md", "pytest tests/test_tickets.py")], "note": "tests/test_tickets.py ya no existe"},
            {"type": "skill_project", "evidence": [(TK_API, "4. Add a test in `tests/test_tickets.py`")], "note": "la skill usa un archivo que ya no existe"},
            {"type": "readme_code", "evidence": [("README.md", "`GET /api/tickets?status=open`"),
                                                 ("helpdesk/routes.py", "def list_tickets(state: str | None = None)")],
             "note": "el parámetro de filtro cambió de status a state, solo lo ve el LLM"},
        ],
    },
]
