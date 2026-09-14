# Simple E-Commerce App

A small e-commerce application: product management, CSV import, search, and checkout with a
simulated payment. Django 5.2 LTS, PostgreSQL 16, server-rendered UI, all running in Docker.

## Running it locally

Requirements: Docker and Docker Compose. Nothing else needs to be installed.

```bash
docker compose up --build
```

The app is on http://localhost:8000. Migrations run automatically on start.

Load the sample catalogue (87 products):

```bash
docker compose run --rm web python manage.py import_products data/products.csv
```

Create a staff user so you can reach the management screens:

```bash
docker compose run --rm -e DJANGO_SUPERUSER_PASSWORD=change-me web \
  python manage.py createsuperuser --noinput --email admin@example.com
```

Customer accounts are created from the sign-up page at http://localhost:8000/accounts/signup/.

Run the tests (239 of them, against a real PostgreSQL database):

```bash
docker compose run --rm web pytest
```

Configuration is read from environment variables. `docker compose up` supplies development
defaults, so no `.env` file is required; `.env.example` documents every variable if you want to
override them.

## Continuous integration

`.github/workflows/ci.yml` runs on every push and every pull request, in two jobs:

- **tests** — Python 3.10 and Poetry against a PostgreSQL service container, running the full
  suite.
- **docker** — builds the image, starts the stack, waits for a real HTTP 200, and imports
  `data/products.csv` through the management command.

The second job exists because "runnable as a docker container" is one of the requirements, and a
broken `Dockerfile` would otherwise leave the test suite green while the thing a reviewer actually
runs is broken. It exercises the whole pipeline in one step: image, migrations, static files,
gunicorn, the database, and the parser against the real file.

The tests job runs natively rather than through Compose because it is roughly three times faster
and Poetry's cache keys cleanly on `poetry.lock`. `DJANGO_SECRET_KEY` is hardcoded in the workflow
on purpose: it is an ephemeral CI database, so treating that value as a secret would be
misleading.

`main` is protected against force pushes and deletion. Pull requests are not required, since this
is a single-author repository.

## What is built

| Requirement | Where |
|---|---|
| Local database | PostgreSQL 16 in Docker, with a named volume |
| CRUD for products | `/staff/products/` (staff only) |
| Import products from CSV | `/staff/import/` and `manage.py import_products` |
| Search for products | `/` — text search plus category and stock filters |
| Purchase products | Cart, checkout with a simulated payment, order history |
| UI for all of the above | Django templates |
| Runnable as a container | `docker compose up --build` |

Beyond the brief, the application has user accounts with two roles (customer and staff),
self-service sign-up, and login-required checkout. The brief does not mention users at all, but a
store where anyone can edit the catalogue is not a store, so I treated the role boundary as part
of the problem rather than an extra.

## The sample CSV

Downloaded on **2026-09-11** and committed at `data/products.csv`, unmodified (CRLF line endings
included — `.gitattributes` stops Git from normalising it, so the file stays byte-identical to
the one provided).

It has 97 data rows and is deliberately dirty. Importing it produces:

```
created 87, updated 0, resurrected 0, rejected 5, blank rows skipped 2
warning: line 36: SKU RS-001 appears more than once; superseded line(s) 2
warning: line 89: SKU BS-021 appears more than once; superseded line(s) 11, 56
rejected: line 7, price: is not a valid decimal number (got 'free')
rejected: line 16, stock: must not be negative (got '-5')
rejected: line 25, name: is required (got '')
rejected: line 41, name: is required (got '     ')
rejected: line 52, category: is required (got '')
```

97 rows − 2 blank − 5 rejected − 3 superseded duplicates = 87 products.

Two rows in the file contain a `<script>` tag and a SQL injection string as product names. Both
are stored exactly as given. Sanitising user data on the way in corrupts it; the defences are
parameterised queries (the ORM) and escaping on the way out (template auto-escaping). There are
tests asserting both that the values survive the import untouched and that they are escaped when
rendered.

## Decisions

### Framework: Django, no DRF

| Option | Why not |
|---|---|
| FastAPI + SQLAlchemy + Pydantic | Best typing story, and the layering falls out naturally. But authentication, sessions, migrations, an admin, and templates are all hand-wired. That plumbing is invisible to a reviewer and expensive in time. |
| Django + DRF | DRF is a serialisation and API layer. With a server-rendered UI, nothing consumes it. It also creates a second definition of "a valid product" next to Django forms, and two validation paths drift. |
| **Django, forms and templates** | **Chosen.** Migrations, authentication, sessions, password hashing, CSRF and the admin come with it, so the time went into the parts that are actually hard: import policy, stock concurrency, payment idempotency. |

I started this challenge planning FastAPI. Deciding to build real user accounts is what changed
the answer: `django.contrib.auth` is well-tested, security-sensitive code that I would otherwise
be writing myself in an afternoon, which is a bad trade.

I did not pull in Pydantic. With Django, forms are the validation layer; adding Pydantic as well
would mean every field's rules existed in two places.

### Database: PostgreSQL

SQLite would satisfy "local DB" and needs no second container. I chose PostgreSQL for two
concrete reasons, not for realism:

- **`NUMERIC(10,2)` is an exact decimal type.** SQLite has none, so prices would be stored as
  floats or as hand-rolled integer cents. Money should not be approximate.
- **Real row-level locking.** The purchase flow depends on `UPDATE ... WHERE stock >= quantity`
  being atomic under concurrency. That is the single most important correctness property in the
  application.

Cost: the app needs Docker Compose rather than a single image. The brief says "runnable as a
docker container"; `docker compose up --build` is one command, which I judged to be the spirit of
it.

### UI: Django templates, no React

A React front end would look better and is what a production store would use. It also means a
second container, a build step, CORS, an API contract, and hand-written loading and error states
for every screen. The brief is explicit that it is more interested in the questions asked than in
the volume of output, so I spent the time on the back end and kept the UI server-rendered with
about 380 lines of hand-written CSS.

No CSS framework either. A CDN link leaves anyone running this offline looking at unstyled HTML,
and vendoring Bootstrap drops a large third-party file into a repository meant to show my work.

### Dependencies: Poetry

I started with a pinned `requirements.txt`, which pinned the six direct dependencies but left ten
transitive ones floating — so the build was pinned, not reproducible. Poetry's lock file resolves
the whole graph with hashes. The alternatives were `pip-tools` (lighter, same lock benefit) and
`uv` (faster, less widely known). Poetry won because the multi-stage `Dockerfile` keeps it out of
the runtime image anyway, so its weight costs nothing at run time.

`pyproject.toml` declares ranges (intent); `poetry.lock` pins exact versions (resolution).
Django is constrained to `<6.0` deliberately: 5.2 is the LTS line, and Python 3.10 cannot run
Django 6 in any case.

### Product model

- **`price` is `DecimalField(max_digits=10, decimal_places=2)`**, mapping to `NUMERIC(10,2)`.
- **`category` is a plain string, not an enum.** The sample data has 18 distinct categories, five
  of them with a single product, and one row with no category at all. A closed enum would reject
  every future category and force a "what happens to Gift Card" answer of "the import fails". A
  lookup table is the production answer and is more than this needs.
- **`stock` is a `PositiveIntegerField`**, which PostgreSQL enforces with a `CHECK (stock >= 0)`.
- **`weight_kg` is nullable.** One row in the sample has no weight, and nothing in the application
  reads the field. Rejecting a product over a value we never use would be wrong.
- Name, SKU and category are also protected by database-level `CHECK` constraints against empty
  strings, so a whitespace-only name cannot be stored by any code path.

### Soft delete, and the partial unique index

Products are never deleted, only marked with `deleted_at`. Hard deletion would either break the
foreign key from order lines or destroy order history.

That choice has a consequence worth spelling out. A plain `UNIQUE` constraint on `sku` combined
with soft delete means a deleted product burns its SKU forever — you could never create a
replacement with the same code. So uniqueness is a **partial** index: unique on `sku` *where
`deleted_at IS NULL`*. Deleted rows can share a SKU; only live ones must be distinct.

Two things follow from this, and both are handled explicitly:

- Django's `ModelForm` does **not** validate a conditional `UniqueConstraint`. Its validator
  evaluates the condition against the submitted fields, `deleted_at` is not one of them, and the
  resulting `FieldError` is swallowed — so a duplicate SKU produced a 500 from the database rather
  than a form error. `ProductForm.clean_sku()` performs the check explicitly.
- Restoring a deleted product can legitimately fail, if a new active product has taken its SKU in
  the meantime. The service catches that and reports it instead of raising.

### CSV import

| Question | Decision | Why |
|---|---|---|
| File vs database | Upsert by SKU | A row in the sample literally reads "Updated lightweight shoes"; insert-only would have rejected it. |
| Duplicates inside one file | Last wins, earlier lines reported as warnings | Consistent with upsert. The duplicates are collapsed before writing, so three rows for one SKU are one write, and the report says "created 1" truthfully. |
| Invalid rows | Skip the row, import the rest, report every rejection with its CSV line number | The sample has 5 bad rows out of 97. All-or-nothing would import nothing and make the application look broken. |
| `$29.99` | Strip the symbol and accept | The intent is unambiguous and the parse is lossless. |
| `free` | Reject | It is not a number. Turning it into 0 invents a business fact the file never states, and a zero-price product is purchasable. |
| Blank optional field on update | Leave the existing value | The file not mentioning a weight is not the same as the file saying there is no weight. |
| SKU matching a deleted product | Restore it | Otherwise the partial index lets a second row appear and "upsert by SKU" quietly stops being true. |
| **`stock` on update** | **Never written** | This is the important one. If import set stock absolutely, re-uploading a catalogue file would reset inventory and discard every sale since the last import, and the store would oversell. Purchases own stock; import only sets it when creating a product or restoring a deleted one. |

Whole-file problems (wrong columns, undecodable bytes, an empty file) are a different case from a
bad row: they reject the upload outright with one message.

The same service function backs the management command and the web upload, so both produce an
identical report. The web upload is capped at 5 MB.

### Purchase

The cart lives in the database rather than the session, keyed to the user. Consequences: adding
to the cart requires logging in, and the product page shows "Log in to buy" for anonymous
visitors instead of an add button. A session cart that merges into the user's cart on login is
what a large store would do; it needs merge-conflict rules and was more than this needs.

The cart holds product references and quantities only — no prices — so it always reflects the
current price.

Checkout runs in one transaction:

1. For each line, claim stock with `UPDATE products SET stock = stock - q WHERE id = ? AND stock >= q`
   and check the row count. The database decides, not the application, so two buyers cannot take
   the same last unit.
2. Create the order and its lines, **snapshotting** product name, SKU and unit price. Prices
   change; an order must remember what was charged.
3. Charge the payment gateway.
4. If the charge is declined, the transaction rolls back: stock is restored, no order exists, and
   the cart is left intact.

**Idempotency.** Each checkout page issues a UUID in a hidden field, stored on the order under a
`UNIQUE` constraint. Submitting twice returns the first order instead of charging again. Double
submission is the most common real bug in a checkout, and it costs almost nothing to prevent.

**The payment gateway** is a `Protocol` with a fake implementation. Any card number is approved
except `4000000000000002`, which always declines — the same convention real payment providers use
for test cards. The card number is passed to the gateway and never stored or logged; there is a
test that reads back every column of the order tables to prove it.

I did not add retries or backoff. There is no remote system to retry against, and code that
sleeps and retries a local function that always succeeds is theatre. Replacing the fake gateway
with a real provider means implementing one interface, and that is where timeouts, retries and
reconciliation would go.

Declined payments leave no record: the transaction rolls back completely and the failure is
logged. A production system would persist failed attempts for support and fraud analysis, which
needs a second transaction or an outbox, since by definition the first one has been rolled back.
Because every stored order is a paid order, `Order` has no `status` field — a column with one
possible value is not worth having.

### Logging

The logs are meant to be operable, not decorative: every state change is recorded, and a whole
process can be followed end to end.

**Output format.** Human-readable by default, so `docker compose logs` stays readable. Setting
`DJANGO_LOG_FORMAT=json` switches to one JSON object per line, where every structured field is a
top-level attribute:

```json
{"timestamp": "2026-09-14T22:25:51+00:00", "level": "INFO", "logger": "ordering.services",
 "message": "Order ORD-2026-00006 placed by user 2 for 94.99", "event": "order.placed",
 "actor_id": 2, "order_reference": "ORD-2026-00006", "amount": "94.99",
 "request_id": "checkout-trace-001"}
```

That shape is the point. A log aggregator can facet on `event` and `actor_id` directly; parsing
prose with a regular expression breaks the first time someone rewords a message. The formatter is
about 25 lines in `config/logging.py` rather than a dependency.

**Event names.** Every log call carries a stable `event` in `<domain>.<action>` form —
`product.created`, `product.stock_adjusted`, `import.completed`, `cart.item_added`,
`checkout.stock_unavailable`, `payment.declined`, `order.placed`, `auth.login_failed`,
`auth.access_denied`. Alerts are then written against `event`, not against message text.

**Request correlation.** A middleware assigns each request an id, held in a `ContextVar` and
injected into every log record by a logging filter. The id is also returned as `X-Request-ID`,
which is how the access log picks up the same value. Filtering on one id gives the whole journey,
application events and HTTP requests interleaved:

```
INFO     cart.item_added     {actor_id: 2, sku: RS-001, quantity: 1}
ACCESS   http.request        {method: POST, path: /cart/add/1/, status: 302, duration_seconds: 0.03}
INFO     checkout.started    {actor_id: 2, lines: 1}
INFO     order.placed        {actor_id: 2, order_reference: ORD-2026-00006, amount: 94.99}
ACCESS   http.request        {method: POST, path: /cart/checkout/, status: 302, duration_seconds: 0.04}
```

An inbound `X-Request-ID` is honoured only if it matches `^[A-Za-z0-9._-]{1,64}$`. Without that
check a client could send a value containing newlines and forge log entries.

**HTTP access logs** come from gunicorn (`gunicorn.conf.py`) and include status, duration and the
request id, so error rate and latency can be monitored without any application changes.

**Command output is not logging.** The import management command writes its report with
`self.stdout.write`, which honours `--verbosity` and can be captured in tests through
`call_command(..., stdout=...)`. Routing the report through `logging` would put it on stderr and
break `manage.py import_products file.csv > report.txt`. The report is for a person; the log line
is for a machine. The service layer logs regardless of who called it — the same importer runs from
a web upload where there is no stdout at all.

**Levels are chosen, not incidental.** One `INFO` on completion with the counts, and one `WARNING`
when any rows were rejected, rather than one line per rejected row. The exception is the
`IntegrityError` branch in the importer, which logs per row with a traceback: a row that passed
validation and was still refused by the database is a bug, not an expected outcome. Declines,
refused stock adjustments, failed logins and denied staff access are all `WARNING`, because those
are the rates worth alerting on.

**Sensitive data.** Card numbers and passwords never reach the logs, and there are tests asserting
both. Events identify people by `actor_id` rather than email, with one deliberate exception:
`auth.login_failed` records the attempted email, because without the identifier you cannot tell
credential stuffing from someone mistyping their own password.

Logs go to stdout with no file handlers — the container writes to the stream and the platform
collects it. `DJANGO_LOG_LEVEL` and `DJANGO_LOG_FORMAT` control level and format.

One thing to watch when adding fields: `extra={"created": ...}` raises
`KeyError: "Attempt to overwrite 'created' in LogRecord"`, because several obvious names
(`created`, `filename`, `module`, `message`) are reserved `LogRecord` attributes. That is why the
import counters are named `products_created` and `rows_rejected`.

### Error pages

- **404** and **403** are styled pages that extend the site layout.
- **A logged-in customer who reaches a staff page** is redirected to the catalogue with a warning
  banner rather than shown a bare 403. That is a deliberate decision at the authorisation layer,
  not a global change to HTTP status codes; anything else that raises `PermissionDenied` still
  returns a real 403.
- **CSRF failures keep their 403** and get their own page. A CSRF failure can be an attack or a
  genuinely broken form, and hiding it behind a friendly banner would be wrong.
- **500 does not redirect.** Django renders the 500 template with no request and no session, so a
  banner (which needs the session) is not merely unwise there, it is impossible. More importantly,
  a 500 means the request failed in an unknown state; turning it into a redirect makes a broken
  application look healthy to logs and uptime checks. The 500 page is standalone — no layout, no
  external CSS — so that a template or static-files failure does not also break the error page.

### Testing

239 tests, running in about six seconds against a real PostgreSQL database rather than SQLite.
Testing on SQLite while production depends on `NUMERIC` precision and row-level locking would
mean the concurrency tests proved nothing.

Tests use a fast password hasher (`conftest.py`). PBKDF2 cost about 1.1 seconds for every test
that created a user and logged in, which was almost the entire runtime — removing it took the
suite from 85 seconds to under 10. The project settings do not override `PASSWORD_HASHERS`, so
production keeps Django's secure default, and a test enforces that the weak hasher cannot leak
out of the test configuration.

The tests worth looking at first:

- `catalog/tests/test_services.py` — stock cannot go negative under concurrent decrements.
- `ordering/tests/test_checkout.py` — declined payment rolls stock back; two buyers cannot take
  the same last unit; a partial failure rolls back every line; order lines keep their snapshotted
  price after the product changes.
- `importing/tests/test_parser.py` — one case per anomaly in the sample file.
- `accounts/tests/test_views.py` — sign-up cannot grant itself staff; login will not redirect to
  another host.
- `config/tests/test_events.py` — every state change emits its event; no password or card number
  ever reaches the logs.

## What I deliberately did not build

The brief says "enterprise-grade", which I read as correctness, validation, error handling, tests
and a reproducible setup — not more layers.

- **Microservices.** The purchase flow needs stock decrement and payment to be atomic. In one
  process that is one transaction; split across services it becomes a distributed transaction
  needing sagas or an outbox, and a partial failure means money taken without stock reserved. That
  is manufacturing the hardest possible bug on purpose.
- **An event bus.** No consumer exists and no work is asynchronous. The outbox pattern is what I
  would add when order events need to reach fulfilment or analytics.
- **Redis.** 87 products fit comfortably in PostgreSQL's shared buffers. Caching would add a
  container, a failure mode and invalidation logic to speed up queries that are already fast.
- **A separate payments service.** See the first point; it would break the transaction boundary
  that makes checkout correct.
- **Email verification, password reset, saved addresses, refunds, multi-currency.** Real stores
  need these. None are in the brief, and half-finishing six features is worse than finishing four.

The architecture is a layered modular monolith: one deployable, Django apps as the domain modules
(`catalog`, `importing`, `ordering`, `accounts`), and a service layer holding the operations that
have real rules — checkout, import policy, stock adjustment. There is no repository layer, because
Django's ORM already is one; wrapping it would add a file per entity for a swappability that will
never be exercised.

## Known limitations

- **The payment gateway is called inside the database transaction.** That gives true atomicity
  against a fake gateway, but against a real provider it means holding row locks across a network
  call. The production shape is: claim stock and commit, charge outside the transaction, then
  confirm or compensate, with the idempotency key making the retry safe.
- Two staff creating the same new SKU within milliseconds of each other will both pass the form
  check and one will get a database error. Correctness holds — the constraint refuses the
  duplicate — but the error presentation is poor.
- Migrations run on container start. That is fine for a single container; with several replicas
  they would race and belong in a separate job.
- The import reads the whole file into memory. Fine at this size, which is why the upload is
  capped.
- The import report is rendered on the POST response, so refreshing re-runs the import. This is
  harmless because the import is idempotent by design, but post/redirect/get would be tidier.
- Test dependencies ship in the runtime image so that the suite can be run without a local Python.
  A production build would use `--only main`.
- Basic pagination, no full-text search. PostgreSQL's `SearchVector` with a GIN index is the
  upgrade when ranking matters; at 87 products `ILIKE` is indistinguishable and simpler.

## Project layout

```
accounts/     users, sign-up, login, the staff authorisation mixin
catalog/      Product model, public catalogue and search, staff CRUD
importing/    CSV parsing, import policy, management command and upload view
ordering/     cart, checkout, payment gateway, orders
config/       settings, root URLs, JSON logging and the request-id middleware
data/         the sample CSV, as downloaded
templates/    base layout, error pages, login
static/       stylesheet
```

## Code style

No inline comments. Docstrings only on public functions whose name and signature do not explain
themselves — for example the import service, where the upsert and stock rules are worth stating
next to the code.
