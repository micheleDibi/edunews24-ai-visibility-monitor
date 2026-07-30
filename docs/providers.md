# Provider: parametri API verificati

> ## ⚠ Gemini: vincolo di licenza, non tecnico
>
> L'adapter Gemini esiste in `app/clients/gemini_client.py` ma e' **disattivato
> per default** (`GEMINI_ENABLED=false`). I termini dell'API Gemini vietano
> esplicitamente cio' che questo servizio fa con i risultati di grounding.
> Verificato su https://ai.google.dev/gemini-api/terms il 2026-07-30, verbatim:
>
> - «You will not, and will not allow your end user or any third party to,
>   cache, frame, syndicate, resell, **analyze**, train on, or otherwise learn
>   from Grounded Results or Search Suggestions.»
> - «For example, using programmatic or automated means to collect Links,
>   **using Links to build an index**, or using Links to identify destination
>   pages for crawling or scraping»
> - «You will only display the Grounded Results with the associated Search
>   Suggestion(s) **to the end user who submitted the prompt**.»
>
> Un monitor di visibilita' manda prompt in modo programmatico, raccoglie i
> Link, li conserva nella tabella `citations` e li analizza per contare quante
> volte compare un dominio, senza mostrarli ad alcun utente finale perche' gira
> headless. Le tre clausole lo descrivono tutte e tre.
>
> Abilitalo solo dopo un parere legale o un permesso scritto da Google.
>
> **Gli altri tre provider sono stati verificati e non hanno vincoli
> equivalenti**: OpenAI non vieta di conservare o analizzare (chiede di usare le
> funzionalita' di citazione e di rendere i link cliccabili quando si mostrano i
> risultati a un utente); Perplexity non ha divieti in materia; i termini
> commerciali di Anthropic non contengono clausole specifiche sul web search.

**Data di verifica: 2026-07-30.** Ricerca condotta sulle documentazioni ufficiali
correnti, non sulla memoria del modello. Ogni campo marcato a confidenza `medium`
o inferiore va riverificato prima di fidarsi del parser: un nome di campo
sbagliato non produce un errore, produce una misura vuota.

> La fase di verifica avversariale su questi report e' stata interrotta (un
> agente bloccato). I quattro report primari sono completi; le verifiche
> incrociate no. Vedi la nota alla fine di ogni sezione.


---

## OpenAI

**Confidenza del report: `high`**


### Meccanismo di web search

yes — hosted server-side tool `{"type": "web_search"}` in the Responses API (POST /v1/responses). The model decides whether/how often to search, executes searches on OpenAI's infrastructure, and returns both `web_search_call` output items and `url_citation` annotations attached to the assistant text. A legacy Chat Completions path still exists but only via the dedicated `gpt-5-search-api` model (always searches, fewer controls).


### Modelli

- `gpt-5.6-luna` — search: True — PRIMARY RECOMMENDATION for the visibility monitor. Explicitly documented as 'designed for cost-sensitive, high-volume workloads'. $1.00 in / $0.10 cached / $6.00 out per 1M. 1,050,000 ctx (922k max input). Knowledge cutoff Feb 2026. Supports web search + structured outputs + function calling. It is also the named REPLACEMENT model for the deprecated gpt-5-nano and gpt-4.1-nano, so it is the safe long-lived choice. Tier1 500 RPM / 500K TPM. Source: https://developers.openai.com/api/docs/models/gpt-5.6-luna.md
- `gpt-5.6` — search: True — Alias that routes to snapshot `gpt-5.6-sol` (frontier). This is the model used in EVERY code sample on the current web-search guide, so it is the best-documented path. $5.00 in / $0.50 cached / $30.00 out per 1M; >272K-token requests cost 2x input / 1.5x output. Use it only if you want the flagship's agentic multi-search behaviour as one of your measured conditions — it is expensive for 200 q/day. Source: https://developers.openai.com/api/docs/models/gpt-5.6.md
- `gpt-5.6-terra` — search: True — Mid-tier GPT-5.6 ('balances performance and cost'), $2.50 in / $0.25 cached / $15.00 out per 1M. It is the documented replacement for the now-shutdown gpt-4o-search-preview models, i.e. OpenAI's own suggested migration target for search workloads. Good middle measurement point. Source: https://developers.openai.com/api/docs/pricing
- `gpt-5.4-nano` — search: True — SECOND TASK WINNER (Italian question rewriting). Snapshot gpt-5.4-nano-2026-03-17. $0.20 in / $0.02 cached / $1.25 out per 1M. 400k ctx. Supports Structured Outputs + function calling. No deprecation notice on the deprecations page — unlike the two nominally cheaper models below. Note: 'Regional processing endpoints incur a 10% cost increase for this model.' Source: https://developers.openai.com/api/docs/models/gpt-5.4-nano.md
- `gpt-5-nano` — search: True — ABSOLUTE CHEAPEST text model still listed: $0.05 in / $0.005 cached / $0.40 out per 1M, 400k ctx, Structured Outputs supported. BUT IT IS DEPRECATED: snapshot gpt-5-nano-2025-08-07 shuts down 2026-12-11 (announced 2026-06-11, replacement gpt-5.6-luna). Only use it if you accept a hard migration in ~4 months. Sources: https://developers.openai.com/api/docs/models/gpt-5-nano.md and https://developers.openai.com/api/docs/deprecations
- `gpt-5-search-api` — search: True — Chat Completions-only search model, 200k context window. Use ONLY if you must keep a Chat Completions integration. It ALWAYS searches before responding (search is not an optional tool), and it does NOT support the Responses-API controls: domain filters, complete source lists, live-access control, returned-token budget. I could NOT find a dedicated model page or a per-1M price row for this id on the current pricing table — treat its token pricing as UNCONFIRMED. Source: https://developers.openai.com/api/docs/guides/tools-web-search


### Richiesta

ENDPOINT: POST https://api.openai.com/v1/responses
AUTH HEADER: `Authorization: Bearer $OPENAI_API_KEY`  +  `Content-Type: application/json`
(Docs confirm the older https://platform.openai.com/docs/* URLs now 301-redirect to https://developers.openai.com/api/docs/*; the API host api.openai.com is unchanged.)

=== MODE A — WEB SEARCH ENABLED (the measurement call) ===
Minimal but complete body, exact current parameter names, verbatim from https://developers.openai.com/api/docs/guides/tools-web-search:

{
  "model": "gpt-5.6-luna",
  "instructions": "Rispondi in italiano.",
  "input": "Quali sono le ultime notizie sulla scuola in Italia?",
  "tools": [
    {
      "type": "web_search",
      "search_context_size": "medium",
      "user_location": {
        "type": "approximate",
        "country": "IT",
        "city": "Roma",
        "region": "Lazio",
        "timezone": "Europe/Rome"
      }
    }
  ],
  "tool_choice": "required",
  "include": ["web_search_call.action.sources"],
  "store": false
}

Notes on each field:
- `"type": "web_search"` is THE current tool type string. Docs verbatim: "For new Responses API integrations, use { \"type\": \"web_search\" }. The earlier `web_search_preview` tool remains available for legacy integrations, but it does not support newer controls such as `filters`, `external_web_access`, and `return_token_budget`."
- `tool_choice` accepts "none" | "auto" | "required", plus object forms. Docs limitation section verbatim: "With `tool_choice: \"auto\"`, search is optional. Use `tool_choice: \"required\"` or a specific web search tool choice when search must run." For a VISIBILITY MONITOR you must use "required" (or {"type":"web_search"}), otherwise some queries will silently answer from parametric memory and pollute your metric.
- `include: ["web_search_call.action.sources"]` is the exact enum string that returns the FULL consulted-URL list (superset of citations). Confirmed verbatim in the "Sources" section curl/python samples.
- System prompt: two equivalent ways — (a) top-level `"instructions": "..."` string, or (b) a message object inside the `input` array: `{"role": "system", "content": "..."}` (the structured-outputs guide uses role "system"; role "developer" is also accepted).
- Optional extras confirmed on the same page: `filters: {allowed_domains: [...max 100], blocked_domains: [...max 100]}` (omit http/https prefix; includes subdomains; Responses-API `web_search` only); `external_web_access: false` for cache-only/offline mode (default true); `return_token_budget: "default" | "unlimited"` (GPT-5+ reasoning only; null/numbers/other strings are REJECTED); `search_content_types: ["image","text"]` + `image_settings: {max_results, caption}`; `background: true` for long runs.

OFFICIAL PYTHON SDK EQUIVALENT (verbatim style from the docs):
from openai import OpenAI
client = OpenAI()
response = client.responses.create(
    model="gpt-5.6-luna",
    instructions="Rispondi in italiano.",
    input="Quali sono le ultime notizie sulla scuola in Italia?",
    tools=[{"type": "web_search", "search_context_size": "medium"}],
    tool_choice="required",
    include=["web_search_call.action.sources"],
)
print(response.output_text)

=== MODE C — NO TOOLS AT ALL (pure parametric memory) ===
Same endpoint, same model, same auth. Simply OMIT the `tools` key entirely. Do NOT send `tools: []` plus nothing else and assume it is equivalent — the documented, unambiguous belt-and-braces form is to omit `tools` AND pin `tool_choice: "none"` ("Model will not call any tool"). Also drop `include`, since `web_search_call.action.sources` is meaningless with no search tool.

{
  "model": "gpt-5.6-luna",
  "instructions": "Rispondi in italiano.",
  "input": "Quali sono le ultime notizie sulla scuola in Italia?",
  "tool_choice": "none",
  "store": false
}

Python:
response = client.responses.create(
    model="gpt-5.6-luna",
    instructions="Rispondi in italiano.",
    input="Quali sono le ultime notizie sulla scuola in Italia?",
    tool_choice="none",
)

In Mode C, `response.output` will contain no `web_search_call` items and `content[0].annotations` will be an empty array — that is exactly your "memory mode" baseline. No $10/1k tool charge is incurred.

=== SECOND TASK — CHEAP ITALIAN REWRITE WITH FORCED JSON ===
Force structured output via `text.format` (this is the CURRENT Responses-API path; `response_format` is the Chat-Completions-only equivalent). CRITICAL: the root of the schema MUST be an object — "Root objects must not be `anyOf` and must be an object". A bare JSON array at root is NOT allowed, so wrap it (`{"domande": [...]}`) and unwrap client-side. Also "All fields must be `required`" and "`additionalProperties: false` must always be set in objects".

{
  "model": "gpt-5.4-nano",
  "instructions": "Riscrivi ogni domanda in italiano naturale e colloquiale, mantenendo il significato.",
  "input": "[\"Qual e il calendario scolastico 2026?\", \"Come funziona la mobilita docenti?\"]",
  "tool_choice": "none",
  "text": {
    "format": {
      "type": "json_schema",
      "name": "domande_riscritte",
      "strict": true,
      "schema": {
        "type": "object",
        "properties": {
          "domande": {
            "type": "array",
            "items": { "type": "string" }
          }
        },
        "required": ["domande"],
        "additionalProperties": false
      }
    }
  }
}

Python:
resp = client.responses.create(
    model="gpt-5.4-nano",
    instructions="Riscrivi ogni domanda in italiano naturale e colloquiale.",
    input=json.dumps(domande, ensure_ascii=False),
    text={"format": {"type": "json_schema", "name": "domande_riscritte",
                     "schema": {...}, "strict": True}},
)
domande = json.loads(resp.output_text)["domande"]

Weaker fallback (valid JSON but NO schema adherence): `text: {"format": {"type": "json_object"}}`.


### Estrazione delle citazioni

=== PRIMARY PATH — STRUCTURED CITATION OBJECTS (this is what you build edunews24.it detection on) ===
EXACT JSON path, verbatim from the official response sample at https://developers.openai.com/api/docs/guides/tools-web-search:

  response.output[]                              # top-level array
    where .type == "message"
      .content[]                                 # array
        where .type == "output_text"
          .text                                  # the answer string
          .annotations[]                         # array of citation objects
            where .type == "url_citation"        # EXACT type string: "url_citation"
              .url                               # string  <- the cited source URL
              .title                             # string  <- page title
              .start_index                       # integer <- char offset into .text
              .end_index                         # integer <- char offset into .text

Verbatim official JSON sample (copy this into your parser tests):
[
  {
    "type": "web_search_call",
    "id": "ws_67c9fa0502748190b7dd390736892e100be649c1a5ff9609",
    "status": "completed",
    "action": { "type": "search", "query": "latest news about AI" }
  },
  {
    "id": "msg_67c9fa077e288190af08fdffda2e34f20be649c1a5ff9609",
    "type": "message",
    "status": "completed",
    "role": "assistant",
    "content": [
      {
        "type": "output_text",
        "text": "On March 6, 2025, several news...",
        "annotations": [
          {
            "type": "url_citation",
            "start_index": 2606,
            "end_index": 2758,
            "url": "https://...",
            "title": "Title..."
          }
        ]
      }
    ]
  }
]
Docs prose confirming the field set: "the `url_citation` annotation object will contain the URL, title and location of the cited source." The four field names url / title / start_index / end_index are CONFIRMED verbatim in the sample. There is NO `quote`, NO `source_id`, NO `snippet` field on url_citation.

Python SDK equivalent (objects, not dicts):
urls = [a.url for item in response.output if item.type == "message"
                for c in item.content if c.type == "output_text"
                for a in c.annotations if a.type == "url_citation"]

=== SECONDARY PATH — FULL CONSULTED-SOURCE LIST (recommended for a visibility monitor) ===
Requires `include: ["web_search_call.action.sources"]` in the request. Path:

  response.output[]
    where .type == "web_search_call"
      .action.sources                            # complete list of URLs consulted

Docs verbatim: "Unlike inline citations, which show only the most relevant references, sources returns the complete list of URLs the model consulted when forming its response. The number of sources is often greater than the number of citations." Real-time third-party feeds appear here labelled `oai-sports`, `oai-weather`, `oai-finance` — filter those out, they are not web URLs. Available on BOTH `web_search` and `web_search_preview`.
IMPORTANT MEASUREMENT DESIGN NOTE: track BOTH metrics separately — "edunews24.it was CITED" (annotations) vs "edunews24.it was CONSULTED/retrieved" (action.sources). They are different funnel stages and the sources set is strictly larger. NOTE: the docs describe `action.sources` as "the complete list of URLs" but do NOT show a verbatim JSON sample of an individual element, so I cannot confirm whether each element is a bare string or an object with a `.url` key — MARK THIS AS LOW CONFIDENCE and probe it empirically on your first real call before writing the parser.

=== IMAGE RESULTS PATH (only if search_content_types includes "image") ===
Requires `include: ["web_search_call.results"]`. Path: response.output[] where .type=="web_search_call" -> .results[] where .type == "image_result" -> fields `image_url`, `source_website_url`, `thumbnail_url`, `caption`. Not needed for your product.

=== INLINE MARKDOWN / BRACKET REFERENCES ===
The assistant text ALSO carries inline citation markers (docs: "By default, the model's response will include inline citations for URLs found in the web search results"), and OpenAI's ToS-level requirement is: "When displaying web results or information contained in web results to end users, inline citations must be made clearly visible and clickable in your user interface." However the inline markers' exact rendering format is NOT specified in the docs. DO NOT regex the text. Use `annotations[]` as your single source of truth — that is precisely what start_index/end_index exist for (they map each annotation onto the character span of `.text` it backs, so you can re-render clickable links yourself).

=== ARE THE URLs DIRECT OR REDIRECT-WRAPPED? ===
DIRECT. The documented field is a plain `"url": "https://..."` — there is no wrapper/redirect object and no `resolved_url` field in the schema. The real domain IS recoverable by simple string parsing (urllib.parse.urlparse(...).netloc) with NO HTTP fetch required. CAVEAT (NOT doc-confirmed, verify empirically): OpenAI has historically appended tracking query params such as `?utm_source=openai` to url_citation URLs. That does not change the host, so your edunews24.it host-match is safe either way, but strip the query string before de-duplicating URLs or you will double-count the same article. I could not find any official page documenting or denying this param — treat it as an empirical check on day one.

=== TOKEN USAGE FIELD ===
Field holding token usage: `response.usage`, containing:
  response.usage.input_tokens                          (integer)
  response.usage.input_tokens_details.cached_tokens    (integer)
  response.usage.output_tokens                         (integer)
  response.usage.output_tokens_details.reasoning_tokens (integer)
  response.usage.total_tokens                          (integer)
(Confirmed at https://developers.openai.com/api/docs/guides/token-counting and the reasoning guide. NOTE: Responses API uses `input_tokens`/`output_tokens` — the Chat Completions API uses the DIFFERENT names `prompt_tokens`/`completion_tokens`, so do not share a billing parser between the two paths. Docs verbatim: "The Responses API reports this total as `output_tokens`, while the Chat Completions API reports it as `completion_tokens`.")
Note that search-result content tokens are folded into `input_tokens` and billed at model rates — this is why a searched call costs far more in tokens than a memory-mode call on the same question.

=== NUMBER OF SEARCHES PERFORMED ===
There is NO scalar counter field. You COUNT output items:

  n_searches = len([i for i in response.output
                    if i.type == "web_search_call" and i.action.type == "search"])

Docs verbatim on the action types: the action is one of
  - `search` — "represents a web search. It will usually (but not always) includes the search `queries` which were searched. Search actions incur a tool call cost."
  - `open_page` — "represents a page being opened. Supported in reasoning models."
  - `find_in_page` — "represents searching within a page. Supported in reasoning models."
BILLING-CRITICAL: only `action.type == "search"` is documented as incurring the per-call charge, so counting ALL `web_search_call` items (including open_page / find_in_page, which reasoning models emit freely) will OVERSTATE your bill. Count the `search` actions specifically.
FIELD-NAME CAUTION: the guide's prose says the search action "includes the search `queries`" (plural) while the official JSON sample shows a singular `"query": "latest news about AI"`. The docs are internally inconsistent here. Do NOT depend on either name — code defensively: `getattr(action, "queries", None) or getattr(action, "query", None)`. The `action.type` string and the item `type` string are the only reliable discriminators. Also read `web_search_call.status` (sample shows `"completed"`) and skip non-completed calls when tallying.


### Prezzi

Observed 2026-07-30 at https://developers.openai.com/api/docs/pricing (the old https://platform.openai.com/docs/pricing 301-redirects here). Built-in-tools anchor: https://developers.openai.com/api/docs/pricing#built-in-tools

WEB SEARCH TOOL — SEPARATE CHARGE, ON TOP OF TOKENS (verbatim rows):
- "Web search (all models)": $10.00 / 1k calls + Search content tokens billed at model rates   -> $0.01 per search call
- "Image Web search (all models)": $10.00 / 1k calls + Search content tokens billed at model rates
- "Web search preview, reasoning models (gpt-5, o-series)": $10.00 / 1k calls + Search content tokens billed at model rates
- "Web search preview, non-reasoning models": $25.00 / 1k calls + Search content tokens are FREE
So the current `web_search` tool = $10 per 1,000 search calls AND the retrieved page content is billed to you as ordinary INPUT TOKENS at your model's rate. Pricing is uniform across models and — importantly — is NOT differentiated by `search_context_size` anywhere in the current table (see gotchas: this is a change from older tiered pricing).
Note the counter-intuitive legacy row: the non-reasoning PREVIEW variant costs 2.5x per call ($25/1k) but gives you the search content tokens for free. For a high-volume grounded-answer monitor on a cheap model, that legacy row can actually be cheaper in total than $10/1k + paying for ~10-50k of retrieved input tokens per call. Model this before choosing.

TEXT MODEL TOKEN PRICES per 1M (input / cached input / output), verbatim rows:
- gpt-5.6-sol (alias `gpt-5.6`): $5.00 / $0.50 / $30.00   (>272K-token requests: 2x input, 1.5x output)
- gpt-5.6-terra:  $2.50 / $0.25 / $15.00
- gpt-5.6-luna:   $1.00 / $0.10 / $6.00
- gpt-5.5 (<272K): $5.00 / $0.50 / $30.00 ; gpt-5.5-pro (<272K): $30.00 / — / $180.00
- gpt-5.4 (<272K): $2.50 / $0.25 / $15.00 ; gpt-5.4-mini: $0.75 / $0.075 / $4.50 ; gpt-5.4-nano: $0.20 / $0.02 / $1.25 ; gpt-5.4-pro: $30.00 / — / $180.00
- gpt-5.2: $1.75 / $0.175 / $14.00 ; gpt-5.2-pro: $21.00 / — / $168.00
- gpt-5.1: $1.25 / $0.125 / $10.00
- gpt-5: $1.25 / $0.125 / $10.00 ; gpt-5-mini: $0.25 / $0.025 / $2.00 ; gpt-5-nano: $0.05 / $0.005 / $0.40 ; gpt-5-pro: $15.00 / — / $120.00
- gpt-4.1: $2.00 / $0.50 / $8.00 ; gpt-4.1-mini: $0.40 / $0.10 / $1.60 ; gpt-4.1-nano: $0.10 / $0.025 / $0.40
- gpt-4o: $2.50 / $1.25 / $10.00 ; gpt-4o-mini: $0.15 / $0.075 / $0.60
- o3: $2.00 / $0.50 / $8.00 ; o4-mini: $1.10 / $0.275 / $4.40
(File search, for contrast: $2.50 / 1k calls + $0.10/GB/day storage with 1 GB free.)
The APIs themselves (Responses, Chat Completions, Batch, Realtime, Assistants) are not priced separately — you pay model token rates plus any tool call fee.

YOUR WORKLOAD SIZED (200 distinct queries/day, OpenAI leg only):
- Search tool fee alone: 200 x $0.01 = $2.00/day = ~$60/month, IF the model performs exactly one search per query. Agentic/reasoning models routinely fire several searches per question, so budget 2-4x that ($120-240/month) unless you pin a non-reasoning model or low reasoning effort.
- Token cost on gpt-5.6-luna assuming ~15k retrieved input tokens + ~800 output tokens per call: 200 x (15k x $1/1M + 0.8k x $6/1M) = 200 x ($0.015 + $0.0048) = ~$4.00/day = ~$120/month.
- Memory-mode (Mode C) calls are dramatically cheaper: no $10/1k fee and only ~200 input tokens, so ~$0.30/month on gpt-5.6-luna. Run the memory-mode arm liberally.
- The rewrite job on gpt-5.4-nano is financially negligible (10 short Italian strings ~ a few hundred tokens): well under $0.01 per run.

I could NOT confirm a per-1M token price row for `gpt-5-search-api` on the current pricing table — its token pricing is UNCONFIRMED.


### Rate limit

Source: https://developers.openai.com/api/docs/guides/rate-limits and the per-model pages.

Limits are per-ACCOUNT-TIER and per-MODEL. The rate-limits guide itself does NOT list per-model RPM/TPM — it says "To view a high-level summary of rate limits per model, visit the models page." Usage tiers (qualification -> monthly usage limit): Free (allowed geography) $100/mo; Tier 1 ($5 paid) $100/mo; Tier 2 ($50 paid) $500/mo; Tier 3 ($100 paid) $1,000/mo; Tier 4 ($250 paid) $5,000/mo; Tier 5 ($1,000 paid) $200,000/mo.

Per-model defaults I confirmed:
- gpt-5.6-luna: Tier1 500 RPM / 500K TPM; Tier2 5K / 2M; Tier3 5K / 4M; Tier4 10K / 10M; Tier5 30K / 180M.
- gpt-5.4-nano: Tier1 500 RPM / 200K TPM; Tier2 5K / 2M; Tier3 5K / 4M; Tier4 10K / 10M; Tier5 30K / 180M.
Web search adds NO separate rate limit — docs verbatim: "Responses API web search uses the underlying model's tiered rate limits" / "Same as tiered rate limits for underlying model used with the tool."

Your ~200 queries/day is roughly 0.14 RPM — you will never approach even Tier 1's 500 RPM. The only realistic constraint is TPM if you fan out many searched calls concurrently: at Tier 1 on gpt-5.4-nano (200K TPM) and ~15-30k retrieved tokens per grounded answer, you would saturate after ~7-13 concurrent grounded calls in a minute. Serialize or cap concurrency at ~5 and you are fine.

THROTTLING RESPONSE:
- HTTP status: 429 Too Many Requests is the standard OpenAI throttling status, but I could NOT find it stated verbatim on the current rate-limits page — MARK AS UNCONFIRMED and detect by status code empirically rather than hard-coding assumptions.
- Headers (CONFIRMED verbatim on the rate-limits page): `x-ratelimit-limit-requests`, `x-ratelimit-limit-tokens`, `x-ratelimit-remaining-requests`, `x-ratelimit-remaining-tokens`, `x-ratelimit-reset-requests`, `x-ratelimit-reset-tokens`, plus project-scoped `x-ratelimit-limit-project-tokens`, `x-ratelimit-remaining-project-tokens`, `x-ratelimit-reset-project-tokens`.
- A `retry-after` header is NOT documented on that page. Do not rely on it; back off using `x-ratelimit-reset-*` or exponential backoff with jitter.
For your daily batch, the Batch API is a 50%-discount option if 24h latency is acceptable (gpt-5.6-luna and gpt-5.4-nano both list Batch as a supported endpoint).


### Trappole

- TOOL_CHOICE IS THE #1 CORRECTNESS TRAP FOR THIS PRODUCT. Docs verbatim: 'With tool_choice: "auto", search is optional. Use tool_choice: "required" or a specific web search tool choice when search must run.' With the default auto, the model will answer some Italian questions straight from memory, emit zero web_search_call items and zero annotations, and your dashboard will read that as 'edunews24.it not cited' when in fact no search ever happened. Always send tool_choice: "required" in Mode A, and additionally assert n_searches > 0 before recording a data point — otherwise discard the sample as invalid rather than scoring it as a miss.
- SEARCH_CONTEXT_SIZE STILL EXISTS BUT ITS COST STORY HAS CHANGED. Values are exactly "low" | "medium" | "high" (docs: 'Use low for simple lookups, medium for a balanced default, and high when the answer may require more detail from search results'). CRITICAL: the current docs state NO default value, and the current pricing table shows NO price differentiation by context size — the single row is '$10.00 / 1k calls' for all models. Older OpenAI pricing had per-context-size tiers ($25/$30/$50 per 1k); that tiering is GONE from the current table. The cost impact today is INDIRECT: a larger context size pulls more search content into your prompt, and those tokens are billed at model input rates. So 'high' costs more via tokens, not via a higher tool fee. Also note 'This setting does not set an exact token count or guarantee a specific number of sources or citations' — you cannot use it to normalize the number of sources across providers.
- THE PER-CALL FEE IS PER SEARCH, NOT PER REQUEST. A single agentic request on a reasoning model can emit many web_search_call items. Only action.type == 'search' incurs the fee ('Search actions incur a tool call cost'); open_page and find_in_page do not. A monitoring run you budgeted at $2/day can easily land at $6-8/day. Log n_searches per request from day one and alert on the distribution.
- DOCS ARE INTERNALLY INCONSISTENT ON THE QUERY FIELD NAME. Prose says the search action 'includes the search `queries`' (plural); the official JSON sample shows singular '"query": "latest news about AI"'. I cannot resolve this from the docs. Do not depend on either — read action.type for classification and defensively try both `queries` and `query` if you want to log what was searched. This does not affect citation extraction (url/title/start_index/end_index are unambiguous).
- action.sources ELEMENT SHAPE IS UNCONFIRMED. The docs describe include:['web_search_call.action.sources'] as returning 'the complete list of URLs the model consulted' but show no verbatim JSON sample of a single element, so I cannot tell you whether elements are bare strings or objects with a .url key. Probe this on your very first real call before committing parser code. Also: 'Real-time third-party feeds are also surfaced here and are labeled as oai-sports, oai-weather, or oai-finance' — those are NOT web URLs and must be filtered out or urlparse will produce garbage hosts.
- SOURCES != CITATIONS, AND THAT DISTINCTION IS YOUR PRODUCT. Docs verbatim: 'The number of sources is often greater than the number of citations.' Store both. 'edunews24.it retrieved but not cited' is a genuinely different and commercially interesting signal from 'edunews24.it cited', and only the sources field exposes it. Providers other than OpenAI may only expose one of the two, so record which signal each provider gives you and never compare a citation rate against a retrieval rate across providers.
- web_search_preview IS LEGACY AND SILENTLY DEGRADES. It does not support `filters` or `return_token_budget`, and it IGNORES `external_web_access` (behaves as if true). If you copy old tutorial code using web_search_preview, your domain filters will be dropped without an error. Use "web_search".
- CHAT COMPLETIONS SEARCH IS A DEAD END FOR NEW BUILDS. gpt-4o-search-preview and gpt-4o-mini-search-preview had shutdown date 2026-07-23 — which is ALREADY IN THE PAST as of today (2026-07-30), so those model ids should be assumed non-functional right now. Only gpt-5-search-api remains on the Chat Completions path, it ALWAYS searches (search is not optional, so you cannot build Mode C on it), and it lacks domain filters, complete source lists, live-access control and returned-token budget. Build on Responses.
- MODEL DEPRECATIONS WILL BITE THIS PROJECT WITHIN MONTHS. gpt-4.1-nano shuts down 2026-10-23 (~3 months away) and gpt-5-nano shuts down 2026-12-11 (~4.5 months away); both name gpt-5.6-luna as the replacement. gpt-4.1 and gpt-4.1-mini are still listed as web-search-capable but are from the same sunsetting generation. Do not hard-code a nano model id in a service meant to run for a year — put model ids in config and pin dated snapshots so a silent alias re-point does not invalidate your longitudinal time series.
- PINNING SNAPSHOTS MATTERS FOR A LONGITUDINAL MONITOR. 'gpt-5.6' is an ALIAS that currently routes to gpt-5.6-sol; aliases get re-pointed. If your product's value is a trend line over months, pin explicit snapshots (e.g. gpt-5.4-nano-2026-03-17) and record the resolved model id returned on every response, so a mid-series model swap is visible in your data rather than being mistaken for a change in edunews24.it's visibility.
- SEARCH CONTEXT IS HARD-CAPPED AT 128K REGARDLESS OF MODEL CONTEXT. Docs verbatim: 'For Responses API web search, the search context window is limited to 128k, even when the model context window is larger.' gpt-5.6-luna's 1.05M window does not help the search leg.
- REASONING-EFFORT LANDMINES. 'Web search does not support gpt-5 with minimal reasoning' and 'gpt-5.4 with reasoning effort set to none may produce lower-quality results'. If you dial reasoning down to save money on a searched call, you can silently break or degrade search. Test your exact (model, reasoning effort) pair before locking it in.
- STRUCTURED OUTPUTS CANNOT RETURN A BARE ARRAY. 'Root objects must not be anyOf and must be an object' — your requested 'JSON array of strings' is ILLEGAL as a root schema. Wrap it: {"domande": ["..."]} and unwrap client-side. Also mandatory under strict: true — every property must appear in `required`, and every object must set additionalProperties: false. Optional fields must be emulated as a union with null.
- RESPONSES vs CHAT COMPLETIONS USE DIFFERENT USAGE FIELD NAMES. Responses: input_tokens / output_tokens / total_tokens. Chat Completions: prompt_tokens / completion_tokens. Docs call this out explicitly. A shared cost-accounting helper across the two paths will silently record zeros.
- DON'T REGEX THE ANSWER TEXT FOR URLs. The inline citation rendering format is not specified in the docs and can change. annotations[] with start_index/end_index is the contract. Note also the ToS-adjacent requirement: 'When displaying web results or information contained in web results to end users, inline citations must be made clearly visible and clickable in your user interface' — relevant if your monitor dashboard shows the raw grounded answers to clients.
- STRIP TRACKING PARAMS BEFORE DEDUPLICATING. url_citation.url is a direct URL (no redirect wrapper, host recoverable by urlparse with no HTTP fetch), but OpenAI has historically appended params like ?utm_source=openai. Not doc-confirmed either way. Host matching for edunews24.it is unaffected, but per-article dedup and cross-provider URL joins will break if you keep the query string. Normalize: lowercase host, strip 'www.', drop query/fragment.
- MATCH ON HOST, NOT SUBSTRING. Searching for the literal 'edunews24.it' anywhere in the URL will false-positive on aggregators and on URLs containing it as a path or query parameter. Parse the netloc and compare after stripping 'www.'. Decide up front whether subdomains count.
- USE user_location FOR ITALIAN QUERIES. Without it, results skew to the API's default geography and Italian-language education queries will under-surface Italian domains, biasing your entire metric against edunews24.it. Set {"type":"approximate","country":"IT","city":"Roma","region":"Lazio","timezone":"Europe/Rome"}. Note user location is NOT supported for deep research models.
- external_web_access: false GIVES YOU A CACHE-ONLY MODE. Default is true. This is a genuinely useful FOURTH measurement arm for your product — 'is edunews24.it in the index at all' vs 'does live search surface it' — and it is OpenAI-specific, so do not try to mirror it across providers.
- return_token_budget IS STRICTLY VALIDATED. Only the strings 'default' and 'unlimited' are accepted; 'null, numbers, and other strings are rejected'. It applies only to the hosted Responses web_search tool with GPT-5+ reasoning models — not to non-reasoning search, legacy paths, Chat Completions search models, or web_search_preview. 'unlimited' increases latency and cost; leave it at default for routine monitoring.
- SET store: false FOR A MEASUREMENT HARNESS. Responses are persisted by default; for 200 calls/day of automated probing you probably do not want server-side retention. Combine with background: true only if you adopt long agentic runs.
- CONSIDER THE BATCH API. Both gpt-5.6-luna and gpt-5.4-nano support the Batch endpoint at a discount, and a daily visibility snapshot tolerates 24h latency perfectly. This is the single biggest cost lever available on the token side (the $10/1k search fee still applies).
- PLATFORM.OPENAI.COM DOC URLS NOW 301 TO DEVELOPERS.OPENAI.COM. If you have doc links or scrapers pointing at platform.openai.com/docs/*, expect cross-host redirects. Markdown versions of any doc page are available by appending .md to the URL — extremely useful for keeping this research reproducible in CI.


### Fonti consultate

- https://developers.openai.com/api/docs/guides/tools-web-search — PRIMARY. Tool type string "web_search", web_search_preview legacy status, full output/citations JSON sample with url_citation + url/title/start_index/end_index, action types search/open_page/find_in_page, tool-call cost statement, search_context_size values, return_token_budget, domain filters, sources + include enum, image results, user_location, external_web_access, Chat Completions limitations table, Responses limitations table, usage notes.
- https://developers.openai.com/api/docs/guides/tools-web-search.md — full raw markdown of the above (all code samples verbatim).
- https://developers.openai.com/api/docs/pricing — text model price table (all rows) and Built-in tools table ($10.00/1k calls web search, $25.00/1k non-reasoning preview with free search content tokens, file search, containers).
- https://developers.openai.com/api/docs/pricing#built-in-tools — anchor cited by the web-search guide for tool call cost.
- https://developers.openai.com/api/docs/models.md — model family listing (GPT-5.6 Sol/Terra/Luna, GPT-5.5, GPT-5 family, GPT-5.1-5.4 variants, cheapest models).
- https://developers.openai.com/api/docs/models/gpt-5.6.md — confirms "gpt-5.6" is an alias routing to gpt-5.6-sol, pricing, >272K surcharge, feature support.
- https://developers.openai.com/api/docs/models/gpt-5.6-luna.md — model id, $1/$0.10/$6, 1,050,000 ctx, Feb 2026 cutoff, endpoints, web search + structured outputs support, per-tier RPM/TPM.
- https://developers.openai.com/api/docs/models/gpt-5.4-nano.md — snapshot gpt-5.4-nano-2026-03-17, $0.20/$0.02/$1.25, 400k ctx, structured outputs + web search, per-tier RPM/TPM, regional +10% note.
- https://developers.openai.com/api/docs/models/gpt-5-nano.md — snapshot gpt-5-nano-2025-08-07, $0.05/$0.005/$0.40, structured outputs + web search, and the recommendation to prefer GPT-5.6 Luna for new cost-sensitive workloads.
- https://developers.openai.com/api/docs/deprecations — gpt-5-nano shutdown 2026-12-11 (replacement gpt-5.6-luna); gpt-4.1-nano shutdown 2026-10-23 (replacement gpt-5.6-luna); gpt-4o-search-preview / gpt-4o-mini-search-preview shutdown 2026-07-23 (replacement gpt-5.6-terra).
- https://developers.openai.com/api/docs/guides/structured-outputs.md — text.format json_schema with name/schema/strict, verbatim Python + curl samples, root-must-be-object rule, all-fields-required rule, additionalProperties:false rule, json_object fallback, supported models.
- https://developers.openai.com/api/docs/guides/token-counting.md — usage field names input_tokens, input_tokens_details.cached_tokens, output_tokens, output_tokens_details.reasoning_tokens, total_tokens; Responses output_tokens vs Chat Completions completion_tokens.
- https://developers.openai.com/api/docs/guides/rate-limits.md — usage tiers table, rate-limit response headers (x-ratelimit-*), pointer to models page for per-model RPM/TPM, no documented retry-after.
- https://developers.openai.com/api/reference/resources/responses/methods/create.md — POST /v1/responses request params (model, instructions, input, tools, tool_choice, include enum values incl. web_search_call.action.sources, text.format, max_output_tokens, store, background, conversation) and response output item types.
- https://developers.openai.com/api/reference/python/resources/responses — tool_choice allowed values ("none" / "auto" / "required" plus object forms) and ResponseUsage fields.
- https://developers.openai.com/api/docs/guides/tools.md — hosted tool type strings available in the Responses API.
- https://developers.openai.com/api/reference/responses/overview — Responses API overview (index only; no field-level detail).


---

## Perplexity (Sonar API + Agent API)

**Confidenza del report: `high`**


Perplexity (Sonar API + Agent API), verified against docs.perplexity.ai on 2026-07-30


### Meccanismo di web search

yes — retrieval is the product. Every `sonar*` model is web-grounded by default (search runs before generation, driven by the user message); on the newer Agent API search is an explicit `{"type":"web_search"}` tool you attach to any model.


### Modelli

- `sonar` — search: True — Cheapest grounded model and the simplest citation extraction path: top-level `search_results` array on a plain OpenAI-shaped chat completion. Ideal for 200 Italian queries/day — at default `search_context_size: "low"` that is 200 x $5/1000 = $1.00/day in request fees plus a few cents of tokens. Use this as the primary.
- `sonar-pro` — search: True — Same response shape, more search depth and follow-up handling, 200K context. Use only if `sonar` under-retrieves on long Italian questions. Costs $3/$15 per 1M tokens plus $6-$14 per 1K requests.
- `perplexity/sonar` — search: True — Same underlying model but via the NEW Agent API (`POST /v1/agent`), which Perplexity now calls the canonical surface (`Sonar Chat Completions is now Agent API`). Token price is far lower ($0.25/$2.50 per 1M) and web search is billed $0.0025 per invocation (= $2.50/1K searches) instead of the $5-$14/1K request fee — roughly half the cost. Trade-off: sources come back inside a typed `output` array, not a flat top-level field, so extraction code is more involved. Recommended if you want to be future-proof.
- `sonar-reasoning-pro` — search: True — Chain-of-thought variant, $2/$8 per 1M + $6-$14/1K requests. Not needed for a visibility monitor — extra reasoning tokens do not improve which sources get cited.
- `sonar-deep-research` — search: True — AVOID for this use case. It runs many searches per call and bills citation tokens ($2/1M), reasoning tokens ($3/1M) and $5 per 1K search queries — cost per query is unpredictable and orders of magnitude higher. Also 5 RPM at Tier 0.


### Richiesta

== OPTION A (RECOMMENDED FOR SIMPLEST CITATION EXTRACTION): Sonar API ==

Endpoint: POST https://api.perplexity.ai/v1/sonar
  (`POST /chat/completions` is ALSO accepted as an alias for OpenAI-SDK compatibility — docs: "Perplexity's canonical Sonar API endpoint is `POST /v1/sonar`. `POST /chat/completions` is also accepted as an alias." Source: https://docs.perplexity.ai/docs/sonar/openai-compatibility)
Auth header: `Authorization: Bearer $PERPLEXITY_API_KEY`
Also: `Content-Type: application/json`

Minimal-but-complete body with search enabled and tuned for your use case:

{
  "model": "sonar",
  "messages": [
    {"role": "system", "content": "Rispondi in italiano, in modo conciso."},
    {"role": "user", "content": "Qual e la migliore scuola superiore di Bari?"}
  ],
  "web_search_options": {
    "search_context_size": "low"
  },
  "search_mode": "web",
  "search_recency_filter": "month",
  "search_domain_filter": ["-pinterest.com"],
  "return_related_questions": false,
  "stream": false
}

Notes on each parameter you asked about (all confirmed on the OpenAPI reference https://docs.perplexity.ai/api-reference/chat-completions-post and https://docs.perplexity.ai/docs/agent-api/tools/web-search):
- `web_search_options.search_context_size` — enum "low" | "medium" | "high", DEFAULT "low". Also drives the per-request price tier. Sibling keys inside `web_search_options`: `search_type` ("fast"|"pro"|"auto"), `user_location` (latitude/longitude/country/city/region), `image_results_enhanced_relevance`.
- `search_domain_filter` — TOP-LEVEL array of strings on the Sonar API. Allowlist = bare domain (`["edunews24.it"]`); denylist = leading minus (`["-reddit.com"]`). Max 20 entries; you may NOT mix allow and deny in the same array. For your monitor, LEAVE IT EMPTY on the measurement queries — filtering to edunews24.it would bias the very metric you are measuring. Use it only for a separate "can it find us at all?" control run.
- `search_recency_filter` — top-level string, enum "hour"|"day"|"week"|"month"|"year".
- Date filters (top-level, MM/DD/YYYY): `search_after_date_filter`, `search_before_date_filter`, `last_updated_before_filter`, `last_updated_after_filter`.
- `return_related_questions` — boolean, top-level. Returns a top-level `related_questions` array of strings.
- `search_mode` — "web" | "academic" | "sec".
- `search_language_filter` — array of ISO 639-1 codes; plus `language_preference` (ISO 639-1) for the ANSWER language. For Italian set `"language_preference": "it"` and/or `"search_language_filter": ["it"]`.
- `enable_search_classifier` (bool) lets the model decide whether to search at all; `disable_search` (bool) turns retrieval off entirely.
- Other standard: `max_tokens` (<=128000), `temperature` (0-2), `top_p`, `stop`, `response_format` (text | json_schema), `stream`, `stream_mode` ("full"|"concise"), `reasoning_effort` ("minimal"|"low"|"medium"|"high"), `return_images`, `image_domain_filter`, `image_format_filter`.

SYSTEM PROMPT: honoured, but ONLY at answer time. Verbatim from https://docs.perplexity.ai/docs/sonar/prompt-guide: "The system prompt is not visible to search; it reaches the model only at answer time, when results are already in hand." and "Do not put search instructions in the system prompt. Phrases like 'search only on Wikipedia' or 'look for the latest results' have no effect." => The retrieval query is derived from the USER message alone. For your monitor this is actually good: keep the system prompt minimal (or omit it) so it cannot perturb the measurement, and put the full Italian question in the user message.

Official SDK equivalent (OpenAI SDK, no modifications needed beyond base_url):

  from openai import OpenAI
  client = OpenAI(api_key=os.environ["PERPLEXITY_API_KEY"], base_url="https://api.perplexity.ai")
  completion = client.chat.completions.create(
      model="sonar",
      messages=[{"role": "user", "content": "..."}],
      extra_body={"web_search_options": {"search_context_size": "low"}},
  )
  for result in completion.search_results:
      print(result["title"], result["url"])

(Perplexity-specific fields such as `search_results` ride along on the OpenAI response object. With httpx you get them natively — for a 4-provider harness httpx is cleaner than fighting `extra_body`/typed models.)

Perplexity also ships a first-party Python SDK: `from perplexity import Perplexity; client = Perplexity()`.

== OPTION B (NEWER, CHEAPER, MORE FUTURE-PROOF): Agent API ==

Endpoint: POST https://api.perplexity.ai/v1/agent   (alias: /v1/responses, kept for back-compat since Mar 2026)
Auth: same Bearer header.

{
  "model": "perplexity/sonar",
  "input": "Qual e la migliore scuola superiore di Bari?",
  "instructions": "Rispondi in italiano.",
  "tools": [
    {
      "type": "web_search",
      "search_context_size": "low",
      "max_results": 10,
      "filters": {"search_recency_filter": "month"}
    }
  ]
}

Note the RELOCATION of parameters vs the Sonar API (source: https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar/how-to):
  messages -> input | max_tokens -> max_output_tokens | system prompt -> `instructions` (top-level string) | search_domain_filter / search_recency_filter / date filters -> inside the web_search tool's `filters` object | search_context_size and user_location -> directly ON the web_search tool, NOT in `filters` | num_search_results -> `max_results` | reasoning_effort -> `reasoning.effort` | enable_search_classifier -> just include the web_search tool | disable_search -> omit the web_search tool or set `max_tool_calls: 0`.
  No Agent-API equivalent for: `search_language_filter`, `stream_mode`, image/video params.

Python SDK: client.responses.create(model=..., input=..., tools=[{"type":"web_search"}], instructions=...)

== MEMORY MODE (no retrieval) ==
- Sonar API: set `"disable_search": true` (present in the OpenAPI schema at https://docs.perplexity.ai/api-reference/chat-completions-post; I could NOT find it described in prose docs, so treat as medium confidence and smoke-test it — check that `search_results` comes back empty and `usage.num_search_queries` == 0).
- Agent API: simply omit the `web_search` tool (or `"max_tool_calls": 0`). This is the clean, documented way, and it also lets you run a non-Perplexity model (e.g. `anthropic/claude-opus-5`, `openai/gpt-5.6-sol`) with zero retrieval.
- There is NO separate offline/chat-only model ID. Perplexity retired the old `llama-3-*-chat`/offline SKUs; today all four `sonar*` models are grounded search models by default. Plainly: you get memory mode via a PARAMETER, not via a model ID.


### Estrazione delle citazioni

AUTHORITATIVE FIELD TODAY = `search_results` (an array of OBJECTS). The old `citations` array-of-URL-strings is the DEPRECATED legacy field.

--- Sonar API (POST /v1/sonar or /chat/completions), NON-STREAMING ---
Primary path (use this):
  response.search_results[].url
  response.search_results[].title
  response.search_results[].date            (publication date)
  response.search_results[].last_updated
  response.search_results[].snippet
Legacy path (fallback only):
  response.citations[]                       -> plain URL strings, same order/1-based index as search_results
Inline markers: response.choices[0].message.content contains bracketed markers `[1]`, `[2]` ... which map 1-based into `search_results` / `citations`. So there are TWO reference forms and you should cover both: (a) the structured `search_results` objects, (b) the `[n]` markdown/bracket markers inside the answer text, resolved via index.
Other top-level keys seen in the doc examples: `id`, `choices`, `created`, `model`, `object`, `usage`, and (when requested) `related_questions`, `images`.

DEPRECATION STATUS — flagging a real inconsistency in Perplexity's own docs: the changelog (https://docs.perplexity.ai/docs/resources/changelog) states for May 2025 "The citations field has been fully deprecated and removed." YET the current OpenAPI reference AND the current example responses on https://docs.perplexity.ai/docs/sonar/features still show a top-level `citations` key alongside `search_results`, and the features page says "Use the links returned in the `citations` or `search_results` fields". CONCLUSION: code against `search_results` as the source of truth; treat `citations` as an optional legacy mirror that may be absent or may disappear without notice. Do NOT build the product on `citations`.

--- Sonar API, STREAMING (`"stream": true`) ---
Search results are NOT streamed progressively. Verbatim from https://docs.perplexity.ai/docs/sonar/features: "Search results and metadata are delivered in the final chunk(s) of a streaming response, not progressively during the stream." You must iterate the whole stream and pick up `chunk.search_results` when it appears (it will be None/absent on all the earlier text deltas). => For a batch visibility monitor, USE stream=false. Streaming buys you nothing and adds a whole failure mode where an aborted stream loses all sources.

--- Agent API (POST /v1/agent), NON-STREAMING ---
  response.output[]  -> find item(s) where item["type"] == "search_results"
      item["queries"][]                  (the search queries the agent actually issued)
      item["results"][].id               (integer, maps to the [n] marker in the answer text)
      item["results"][].url
      item["results"][].title
      item["results"][].snippet
      item["results"][].date
      item["results"][].source           (e.g. "web")
      item["results"][].last_updated
  Answer text: response.output[] item where type == "message" -> content[] where type == "output_text" -> .text   (convenience alias: response.output_text)
  IMPORTANT: there can be MORE THAN ONE `search_results` output item (one per search the agent ran). Accumulate across all of them, do not take the first.
  There is NO top-level `citations` and NO top-level `search_results` on the Agent API. Verbatim from the migration guide: citations are "embedded directly in the answer text, not in a separate field"; the sources live in the `search_results` output item.

--- Agent API, STREAMING ---
  SSE event type `response.reasoning.search_results`, one event per search; sources at `event.results[]` (same object shape). Accumulate across every event.

--- URL FORM ---
Direct, plain URLs. In every official example the `url` is the real destination (e.g. "https://www.ibm.com/think/news/ai-tech-trends-predictions-2026") — NOT redirect-wrapped, NOT a tracking proxy, NO Vertex/Bing-style opaque redirector. The registrable domain is recoverable with `urllib.parse.urlsplit(url).hostname` with ZERO extra HTTP fetches. This is the single biggest operational advantage of Perplexity over Gemini grounding for your edunews24.it matching, and it means you can safely do exact-host matching (remember to strip a leading "www."). Confidence: high for `url`; I did not find an explicit doc sentence promising URLs are never wrapped, so add a one-line assertion in your ingest that hostname is not perplexity.ai.

--- TOKEN USAGE FIELD ---
Sonar API: `usage` object ->
  usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
  usage.citation_tokens, usage.reasoning_tokens,
  usage.search_context_size  (string, echoes the tier actually billed — log this, it is your cost audit trail),
  usage.cost.{input_tokens_cost, output_tokens_cost, reasoning_tokens_cost, request_cost, citation_tokens_cost, search_queries_cost, total_cost}
  -> `usage.cost.total_cost` gives you the exact USD for that call, per-request fee included. Persist it; it removes all guesswork from your cost dashboard.
Agent API: `usage.input_tokens`, `usage.output_tokens`, `usage.total_tokens`.

--- NUMBER OF SEARCHES PERFORMED ---
Sonar API: `usage.num_search_queries` (integer). This is the count of retrieval queries the model actually issued.
Agent API: no equivalent scalar counter found; derive it as `sum(len(item["queries"]) for item in output if item["type"]=="search_results")`, or count the `response.reasoning.search_results` stream events. Cross-check against `usage.cost` / billing since web_search is billed $0.0025 per invocation.


### Prezzi

Observed 2026-07-30. Official page: https://docs.perplexity.ai/docs/getting-started/pricing (also reachable as /getting-started/pricing).

YES — Perplexity still charges a SEPARATE per-request search fee ON TOP of tokens, and it is TIERED BY `search_context_size`. It is quoted PER 1,000 REQUESTS (not per search, not per 1000 searches) for the standard Sonar models.

SONAR API — token prices (USD per 1M tokens):
  sonar                : input $1.00  / output $1.00
  sonar-pro            : input $3.00  / output $15.00
  sonar-reasoning-pro  : input $2.00  / output $8.00
  sonar-deep-research  : input $2.00  / output $8.00

SONAR API — request fee (USD per 1,000 REQUESTS), by web_search_options.search_context_size:
  model                 low     medium   high
  sonar                 $5      $8       $12
  sonar-pro             $6      $10      $14
  sonar-reasoning-pro   $6      $10      $14
  Default context size is "low" if you omit web_search_options.

sonar-deep-research does NOT use the flat per-request fee. It bills instead:
  citation tokens $2 per 1M, reasoning tokens $3 per 1M, and search queries $5 per 1,000 SEARCH QUERIES (a single call can issue many).

AGENT API (POST /v1/agent) — different, cheaper structure: pure token price + per-TOOL-INVOCATION fee.
  perplexity/sonar : input $0.25 / 1M, output $2.50 / 1M, cache $0.0625 / 1M
  Tool fees: web_search $0.0025 per invocation  (= $2.50 per 1,000 searches)
             fetch_url $0.00025 per invocation
             people_search $0.005 per invocation
             finance_search $0.005 per invocation
             sandbox session $0.03 per session
  Third-party models are passed through at first-party provider rates with no markup (e.g. anthropic/claude-opus-5 $5/$25, anthropic/claude-sonnet-5 $2/$10, openai/gpt-5-mini $0.25/$2, google/gemini-3.5-flash $1.50/$9.00).

SEARCH API (the standalone, non-LLM retrieval endpoint): $5.00 per 1,000 requests.

YOUR BUDGET (200 queries/day, Perplexity only):
  sonar @ low context, Sonar API : 200 x $0.005 = $1.00/day request fee + roughly $0.10-$0.20/day tokens => about $33-36/month.
  perplexity/sonar via Agent API with one web_search per call: 200 x $0.0025 = $0.50/day + ~$0.10/day tokens => about $18/month. Roughly half.
  sonar-pro @ low : 200 x $0.006 = $1.20/day request fee + noticeably more token cost (output $15/1M) => about $45-60/month.
  AVOID sonar-deep-research at 200/day — unbounded search-query billing.


### Rate limit

Source: https://docs.perplexity.ai/docs/admin/rate-limits-usage-tiers

Tiers are by CUMULATIVE lifetime API credit purchase (Tier 0 = no purchase, up to Tier 5 at $5,000). Tiers are permanent once reached — no downgrade. Enforcement is a leaky-bucket algorithm (burst allowed, then sustained rate).

Agent API (/v1/agent):
  Tier 0: 1 QPS / 50 req-min
  Tier 1: 3 QPS / 150 req-min
  Tier 2: 8 QPS / 500 req-min
  Tier 3: 17 QPS / 1,000 req-min
  Tier 4: 33 QPS / 2,000 req-min
  Tier 5: 33 QPS / 2,000 req-min

Sonar API: per-model, per-tier. Default for the standard online sonar models is 50 requests/min at the base tier. sonar-deep-research is much tighter: 5 RPM at Tier 0 scaling to 100 RPM at Tier 5.

Search API: 50 query units/second with 50 query units burst, uniform across all tiers.

Throttling: HTTP 429 "Too Many Requests". The docs do NOT document any `Retry-After` or `X-RateLimit-*` response headers — I could not confirm their existence from an official page, so do not build your backoff on them. Implement exponential backoff with jitter on 429 and read the headers opportunistically (log whatever comes back) rather than depending on them. Confidence on the absence of headers: medium (absence of documentation, not documented absence).

For your workload (200 queries/day x 1 provider = ~8/hour) even Tier 0 at 50 RPM is ~360x headroom. Just cap concurrency at 1-2 QPS and you will never see a 429.


### Trappole

- THE BIG ONE — `citations` is deprecated, `search_results` is the field you must build on. The changelog says `citations` was 'fully deprecated and removed' in May 2025, yet the current OpenAPI schema and current doc examples still show it. Parse `search_results[].url` as primary; treat `citations[]` as an optional legacy mirror that may vanish. If you build citation extraction on `citations`, your monitor will silently return zero sources the day they finish the removal.
- Perplexity is mid-migration: `Sonar Chat Completions is now Agent API`. The Sonar chat surface still works (canonical path `POST /v1/sonar`, with `POST /chat/completions` kept as an OpenAI-SDK alias), but it carries an explicit supersession banner. Isolate ALL Perplexity request/response handling behind one adapter class so you can swap to /v1/agent without touching the rest of the service. The response shapes are genuinely different — flat top-level `search_results` on Sonar vs a typed `output[]` array with `type == "search_results"` items on Agent.
- The system prompt does NOT influence retrieval. Verbatim: 'The system prompt is not visible to search; it reaches the model only at answer time.' Search is seeded by the USER message ONLY. Any Italian instruction like 'cerca solo su siti italiani' in a system prompt is a no-op — use `search_domain_filter` / `search_language_filter` / `search_recency_filter` instead. Corollary for your methodology: to compare fairly across 4 providers, keep the system prompt empty or trivially short on Perplexity, because it cannot affect which sources are retrieved anyway.
- DO NOT put edunews24.it in `search_domain_filter` on your measurement queries. Allowlisting your own domain guarantees it appears and destroys the metric. Run it unfiltered; use domain filtering only for a separate control experiment ('is edunews24.it indexed/retrievable at all?').
- `search_context_size` is a PRICE DIAL, not just a quality dial: low/medium/high map to $5/$8/$12 per 1K requests on `sonar` and $6/$10/$14 on `sonar-pro`. Default is 'low'. Forgetting to pin it explicitly is fine (low is the cheap default) — but if a teammate bumps it to 'high' your bill nearly triples. Pin it explicitly in code and log `usage.search_context_size` from every response to verify what was actually billed.
- Streaming loses you nothing and costs you reliability: search results arrive only in the FINAL chunk(s) of a Sonar stream, never progressively. A dropped connection mid-stream = answer text but zero sources. Use `stream: false` for a batch monitor.
- On the Agent API there can be MULTIPLE `search_results` output items (and multiple `response.reasoning.search_results` SSE events) in one response — one per search the agent ran. Accumulate across all of them. Taking only the first item is a subtle bug that will under-count edunews24.it appearances on multi-step queries.
- Agent API `id` fields are per-search-result-item integers that map to the `[n]` markers in the answer text. If you accumulate results across multiple search_results items, the `id` values are NOT globally unique across items — do not use `id` as a dedup key. Dedup on normalized URL (lowercase host, strip 'www.', strip tracking query params).
- There is no offline/chat-only model ID any more. All four `sonar*` models are grounded search models. Memory mode is a PARAMETER: `disable_search: true` on the Sonar API (present in the OpenAPI schema but NOT described in prose docs — verify empirically, confidence low), or on the Agent API simply omit the `web_search` tool / set `max_tool_calls: 0` (documented, confidence high). If you want a true 'what does the model know without search' baseline, use the Agent API with no tools — and note you can even run `anthropic/claude-opus-5` or `openai/gpt-5.6-sol` through it, which may be cheaper than a separate provider integration.
- `search_domain_filter` accepts max 20 entries and CANNOT mix allowlist and denylist in the same array (bare domain = allow, '-domain' = deny). Mixing them silently misbehaves.
- Cost accounting is easy here and you should exploit it: the Sonar API returns `usage.cost.total_cost` (plus a breakdown incl. `request_cost` and `search_queries_cost`) on every response. Persist it per call. Do not try to recompute cost from your own token math — the per-request tier fee makes hand-rolled estimates wrong.
- For a pure visibility monitor, consider the standalone Search API ($5/1K requests) as a CHEAPER SECOND SIGNAL: it returns ranked sources without paying an LLM to write an answer. It measures 'is edunews24.it retrievable for this query' rather than 'does the AI answer cite edunews24.it' — different metric, but a useful control and it isolates whether a miss is a retrieval failure or a citation-selection failure.
- Date fields are inconsistent in format across surfaces: request-side date filters are MM/DD/YYYY strings (`search_after_date_filter: "01/01/2026"`), while response-side `date` is ISO 'YYYY-MM-DD' and `last_updated` is a full ISO timestamp ('2026-02-23T20:10:25'). Parse defensively and never assume they are the same type.
- The Agent API renames things in ways that will bite a copy-paste migration: `messages`->`input`, `max_tokens`->`max_output_tokens`, system prompt->`instructions` (top-level string, not a message role), and ALL search filters move inside the web_search tool's `filters` object — EXCEPT `search_context_size` and `user_location`, which sit directly on the tool, not in `filters`. `search_language_filter` and `stream_mode` have no Agent API equivalent at all.
- Tier 0 gives 50 RPM on standard sonar models but only 5 RPM on sonar-deep-research. If you ever experiment with deep research from your single Docker container, throttle to 1 concurrent request or you will 429 immediately.
- 429 responses are documented, but `Retry-After` / `X-RateLimit-*` headers are NOT documented. Write your backoff to work without them.


### Fonti consultate

- https://docs.perplexity.ai/api-reference/chat-completions-post — full OpenAPI schema: endpoint POST https://api.perplexity.ai/v1/sonar, all request params (search_domain_filter, search_recency_filter, web_search_options.search_context_size, return_related_questions, search_mode, disable_search, enable_search_classifier, language_preference, date filters), and all response fields incl. citations, search_results, usage.num_search_queries, usage.cost.*
- https://docs.perplexity.ai/api-reference — Agent API endpoint POST https://api.perplexity.ai/v1/agent, ResponsesRequest/ResponsesResponse, streaming SSE
- https://docs.perplexity.ai/docs/sonar/overview — canonical Sonar endpoint, curl example, example response JSON, 'Sonar Chat Completions is now Agent API' supersession banner
- https://docs.perplexity.ai/docs/sonar/features — search_results sub-fields (title, url, date, last_updated, snippet); 'Search results and metadata are delivered in the final chunk(s) of a streaming response, not progressively during the stream.'; top-level keys of example responses incl. both citations and search_results
- https://docs.perplexity.ai/docs/sonar/prompt-guide — 'The system prompt is not visible to search; it reaches the model only at answer time, when results are already in hand.' / 'Do not put search instructions in the system prompt.'
- https://docs.perplexity.ai/docs/sonar/openai-compatibility — base_url https://api.perplexity.ai, OpenAI SDK example, '/chat/completions is also accepted as an alias', search_results accessible via the OpenAI response object
- https://docs.perplexity.ai/docs/getting-started/pricing — Sonar token prices, per-1K-request fees by low/medium/high context, Deep Research citation/reasoning/search-query billing, Agent API token prices and per-invocation tool fees ($0.0025 web search), Search API $5/1K
- https://docs.perplexity.ai/docs/getting-started/models — model IDs sonar, sonar-pro, sonar-reasoning-pro, sonar-deep-research; all perform web search
- https://docs.perplexity.ai/docs/agent-api/models — Agent API vendor-prefixed model IDs (perplexity/sonar, anthropic/claude-opus-5, openai/gpt-5.6-sol, google/gemini-3.5-flash, xai/grok-4.5, ...)
- https://docs.perplexity.ai/docs/agent-api/quickstart — curl + Python example, full example response with output[] containing type:'search_results' (queries, results[].id/title/url/snippet/date/source/last_updated) and type:'message', `instructions` param for system guidance
- https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar/how-to — full Sonar->Agent parameter mapping table; 'citations are embedded directly in the answer text, not in a separate field'
- https://docs.perplexity.ai/docs/agent-api/tools/web-search — web_search tool JSON schema: search_context_size (low=300/medium=1000/high=4000 tokens), max_results, max_tokens_per_page, filters{search_domain_filter (max 20, allow OR deny not both), search_recency_filter, date filters}, user_location
- https://docs.perplexity.ai/docs/cookbook/articles/streaming-citations/README — streaming: 'Search results arrive via response.reasoning.search_results events — one event per search the model runs', accumulate event.results
- https://docs.perplexity.ai/docs/resources/changelog — May 2025: 'The citations field has been fully deprecated and removed.'; Apr 2025 citation-token billing removed; Mar 2026 canonical Agent endpoint moved to /v1/agent with /v1/responses alias; Feb 2026 Agent API + Embeddings API GA
- https://docs.perplexity.ai/docs/admin/rate-limits-usage-tiers — tier table (Tier 0 1 QPS/50 RPM ... Tier 5 33 QPS/2000 RPM), sonar-deep-research 5->100 RPM, leaky bucket, HTTP 429


---

## Google Gemini

**Confidenza del report: `medium`**


Google Gemini — Gemini Developer API (AI Studio API key), host `generativelanguage.googleapis.com`. Vertex AI is NOT required: Google Search grounding is fully available on the Developer API with a plain AI Studio key. IMPORTANT STRUCTURAL CHANGE since older knowledge: as of Dec 2025 / GA June 2026 there are now TWO APIs, and they return citations in COMPLETELY DIFFERENT SHAPES: (a) the new Interactions API (`POST /v1beta/interactions`, GA, "recommended for all new projects"), which returns inline `url_citation` annotations, and (b) the legacy `generateContent` API (still "fully supported" but labelled legacy), which returns the classic `groundingMetadata` block. Which one you pick decides whether you get real publisher URLs or vertexaisearch redirect wrappers — see citation_extraction and gotchas.


### Meccanismo di web search

yes — declare the built-in `google_search` tool. Interactions API: `"tools": [{"type": "google_search"}]`. Legacy generateContent: `"tools": [{"google_search": {}}]` (Python: `types.Tool(google_search=types.GoogleSearch())`). The historical `google_search_retrieval` key is explicitly described as for older models only; docs state "For all current models, use the google_search tool ... Older models use a google_search_retrieval tool." A separate `url_context` tool exists (`{"type": "url_context"}`) and can be combined with google_search. Source: https://ai.google.dev/gemini-api/docs/interactions/google-search and https://ai.google.dev/gemini-api/docs/generate-content/google-search


### Modelli

- `gemini-3.6-flash` — search: True — Current stable flagship Flash, explicitly listed as supporting Google Search grounding, and the model used in every official grounding code example (both Interactions and legacy). Best default for a monitor: stable id (no 2-week preview deprecation risk), good multilingual/Italian quality, $1.50/$7.50 per 1M tokens. Grounding billed per SEARCH QUERY at $14/1k after 5,000 free prompts/month shared across Gemini 3 — so cost scales with how many searches the model chooses to fire, not with your request count.
- `gemini-2.5-flash` — search: True — By far the cheapest option at your volume: grounding free tier is 1,500 grounded requests PER DAY, which fully covers ~200 queries/day at zero grounding cost (vs $14/1k queries on Gemini 3). Billed per grounded PROMPT ($35/1k after the free tier), which is predictable — one request equals one charge regardless of how many searches it runs. Tokens $0.30/$2.50. Trade-off: older generation, and it is the classic groundingMetadata-shaped path, so verify it still returns direct urls under the Interactions API before relying on it for domain extraction.
- `gemini-2.5-pro` — search: True — Use only as a quality cross-check arm, not the main workhorse. Grounding-supported, 1,500 RPD free then $35/1,000 grounded prompts, tokens $1.25/$10.00 for prompts <=200k. Stronger reasoning may change which sources it decides to cite, which is itself a useful second datapoint for AI-visibility measurement, but it makes your time series more expensive without changing the citation-extraction code.
- `gemini-3.1-pro-preview` — search: True — Highest-capability Gemini currently listed and grounding-supported ($2.00/$12.00 per 1M for <=200k prompts), but it is a PREVIEW model: docs warn preview models have more restrictive rate limits and 'will be deprecated with at least 2 weeks notice'. Do NOT pin this in a long-running longitudinal monitor — a mid-series deprecation would break your comparability. Include only as an optional experimental arm.


### Richiesta

=== PATH A (RECOMMENDED for your use case): Interactions API ===
Endpoint / method: POST https://generativelanguage.googleapis.com/v1beta/interactions
Auth header: `x-goog-api-key: $GEMINI_API_KEY`  (plus `Content-Type: application/json`)

Verbatim curl from https://ai.google.dev/gemini-api/docs/interactions/google-search :
curl -X POST "https://generativelanguage.googleapis.com/v1beta/interactions" \
      -H "x-goog-api-key: $GEMINI_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{
        "model": "gemini-3.6-flash",
        "input": "Who won the euro 2024?",
        "tools": [{"type": "google_search"}]
      }'

Minimal-but-complete body for your Italian query, with system prompt:
{
  "model": "gemini-3.6-flash",
  "system_instruction": "Rispondi in italiano.",
  "input": "Qual e' la migliore scuola superiore di Milano?",
  "tools": [{"type": "google_search"}],
  "store": false
}
- `system_instruction` (string, optional) is the documented way to pass a system/developer prompt. It is interaction-scoped and must be re-sent on every request.
- `store` (bool) controls server-side storage of the interaction; `store: false` opts out but then disables `previous_interaction_id` and background execution. Fine for your stateless one-shot queries.
- Other documented config: `max_output_tokens`, `temperature`, `seed`, `stop_sequences`, `thinking_level` ("minimal"|"low"|"medium"|"high"), `stream`, `background`.
- Optional tool config: `{"type": "google_search", "search_types": ["web_search"]}` — allowed values per https://ai.google.dev/api/interactions-api are `web_search`, `image_search`, `enterprise_web_search`. NOT documented: any excluded_domains / time-range filter.

Official SDK (google-genai, current PyPI version 2.15.0, requires Python >=3.10; Interactions API requires >= 2.3.0):
from google import genai
client = genai.Client()   # reads GEMINI_API_KEY / GOOGLE_API_KEY from env
interaction = client.interactions.create(
    model="gemini-3.6-flash",
    input="Who won the euro 2024?",
    tools=[{"type": "google_search"}],
)
print(interaction.output_text)
(Package name is `google-genai`, import `from google import genai`. The old `google-generativeai` / `import google.generativeai as genai` package is the deprecated one — do not use it.)

MEMORY MODE (search disabled): `tools` is documented as optional — simply OMIT the `tools` field entirely (do not send `"tools": []`, omit the key). No tool is enabled by default, so the model answers from parametric memory only.

=== PATH B: legacy generateContent (only if you need groundingMetadata semantics) ===
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent
Headers: `x-goog-api-key: $GEMINI_API_KEY`, `Content-Type: application/json`
Body (verbatim from docs):
{
  "contents": [{"parts": [{"text": "Who won the euro 2024?"}]}],
  "tools": [{"google_search": {}}]
}
System prompt here is `"system_instruction": {"parts": [{"text": "..."}]}` (top level, sibling of contents).
SDK:
from google import genai
from google.genai import types
client = genai.Client()
grounding_tool = types.Tool(google_search=types.GoogleSearch())
config = types.GenerateContentConfig(tools=[grounding_tool])
response = client.models.generate_content(
    model="gemini-3.6-flash", contents="Who won the euro 2024?", config=config)
print(response.text)
Memory mode: omit `tools` from GenerateContentConfig.


### Estrazione delle citazioni

=== PATH A — Interactions API (this is the one that solves your redirect problem) ===
Exact JSON paths (verbatim from the response example at https://ai.google.dev/gemini-api/docs/interactions/google-search):
- Cited sources: `response.steps[].content[].annotations[].url`
  Filter: step where `steps[].type == "model_output"`, content element where `content[].type == "text"`, annotation where `annotations[].type == "url_citation"`.
  Full UrlCitation field set (from https://ai.google.dev/api/interactions-api): `type` (always "url_citation"), `url` ("The URL"), `title` ("The title of the URL"), `start_index` ("Start of segment of the response that is attributed to this source"), `end_index` ("End of the attributed segment, exclusive"). There is NO `domain` field.
- Search queries the model ran: `response.steps[].arguments.queries[]` where `steps[].type == "google_search_call"`.
- Search Suggestions HTML (display-required): `response.steps[].result[].search_suggestions` where `steps[].type == "google_search_result"`.
- SDK convenience: `interaction.output_text` for the plain text.
These are INLINE markdown-free structured annotations — there are no bracket-style [1] references to parse; the citation objects carry the offsets. Do not attempt regex extraction from the text.

ARE THE URLs DIRECT? In the official documented example they ARE direct publisher URLs, not redirect wrappers — the literal values shown are `"https://www.aljazeera.com/sports/euro-2024-final"` and `"https://www.uefa.com/euro2024/news/spain-wins-euro-2024"`, with `title` = `"aljazeera.com"` / `"uefa.com"`. The words "redirect", "vertexaisearch" and "expire" do NOT appear anywhere on that page. So for the Interactions API the real domain IS recoverable with ZERO HTTP fetches — `urlparse(url).netloc` and match `edunews24.it` directly. CAVEAT (why my confidence is medium, not high): the API reference describes `url` only as "The URL" — there is no normative sentence guaranteeing it is the origin publisher URL rather than a wrapper, and I found no changelog entry announcing the switch away from redirect links. TREAT AS "very likely but must be empirically confirmed": on day one, fire one live grounded call and assert that no returned `url` host is `vertexaisearch.cloud.google.com`. Keep a resolver fallback behind a feature flag.

=== PATH B — legacy generateContent `groundingMetadata` (VERBATIM field names) ===
Root: `response.candidates[].groundingMetadata`
- `groundingMetadata.webSearchQueries[]` — array of strings, the queries the model issued.
- `groundingMetadata.searchEntryPoint.renderedContent` — string of HTML+CSS for the Search Suggestions widget (display required).
- `groundingMetadata.groundingChunks[]` — each element `{"web": {"uri": ..., "title": ...}}`
  - `groundingChunks[].web.uri` — REDIRECT WRAPPER: documented example value is literally `"https://vertexaisearch.cloud.google.com....."` (real form `https://vertexaisearch.cloud.google.com/grounding-api-redirect/<opaque-token>`). The real publisher domain is NOT recoverable without an HTTP fetch.
  - `groundingChunks[].web.title` — in practice the bare domain string, e.g. `"aljazeera.com"`, `"uefa.com"` — NOT the article headline. Usable as a weak domain signal but it is not the URL and is not documented as a canonical domain field.
  - `groundingChunks[].web.domain` — NOT documented on the Gemini Developer API grounding page. It exists in some generated client typings (`GroundingChunkWeb.domain`) but is reported by developers to come back `None` on the Developer API (googleapis/python-genai issue #1512, open, p3, no official reply). DO NOT rely on it — LOW confidence.
- `groundingMetadata.groundingSupports[]` — each element:
  - `.segment.startIndex`, `.segment.endIndex`, `.segment.text` (offsets into the answer text)
  - `.groundingChunkIndices[]` — integer indices into `groundingChunks[]`
  - `.confidenceScores[]` — present in some client typings but NOT shown in the current Developer API doc example; treat as unreliable/possibly absent.

=== TOKEN USAGE & NUMBER OF SEARCHES PERFORMED ===
Interactions API `usage` object (from https://ai.google.dev/api/interactions-api): `usage.total_input_tokens`, `usage.total_output_tokens`, `usage.total_thought_tokens`, `usage.total_tool_use_tokens`, `usage.total_cached_tokens`, `usage.total_tokens`, plus `usage.input_tokens_by_modality[]`, `usage.output_tokens_by_modality[]`, `usage.cached_tokens_by_modality[]`.
NUMBER OF SEARCHES (your billing driver on Gemini 3): `usage.grounding_tool_count[]` — documented as covering `google_search`, `google_maps`, `retrieval`. Cross-check with `len(steps[type=="google_search_call"].arguments.queries)`.
Legacy generateContent: `response.usageMetadata.promptTokenCount` / `.candidatesTokenCount` / `.totalTokenCount` (plus `thoughtsTokenCount`); search count = `len(groundingMetadata.webSearchQueries)`.


### Prezzi

Observed 2026-07-30 at https://ai.google.dev/gemini-api/docs/pricing

GROUNDING WITH GOOGLE SEARCH — charged SEPARATELY from tokens, and the billing UNIT differs by model generation:
- Gemini 3.x family (gemini-3.6-flash, gemini-3.5-flash, gemini-3.1-pro-preview): "5,000 prompts per month (free, shared across Gemini 3), then $14 / 1,000 search queries". NOTE THE UNIT: per SEARCH QUERY, not per request — "your project is billed for each search query that the model decides to execute" and "If the model decides to execute multiple search queries to answer a single prompt, this counts as multiple billable uses of the tool for that request." Empty web search queries are not billed. (Gemini 3 grounding billing began 2026-01-05 per the changelog.)
- Gemini 2.5 Pro: "1,500 RPD (free), then $35 / 1,000 grounded prompts" — per PROMPT/request, regardless of how many queries it fires.
- Gemini 2.5 Flash: "1,500 RPD (free, limit shared with Flash-Lite RPD), then $35 / 1,000 grounded prompts".

TOKEN PRICES (USD per 1M tokens, standard tier):
- gemini-3.6-flash: input $1.50 / output $7.50
- gemini-3.5-flash: input $1.50 / output $9.00
- gemini-3.1-pro-preview: input $2.00 / output $12.00 (prompts <=200k tokens; higher above)
- gemini-2.5-pro: input $1.25 / output $10.00 (<=200k tokens; higher above)
- gemini-2.5-flash: input $0.30 / output $2.50

COST FOR YOUR WORKLOAD (~200 grounded queries/day ≈ 6,000/month, Gemini arm only):
- gemini-3.6-flash: 5,000 free prompts/month (shared across ALL Gemini 3 models), then $14/1k SEARCH QUERIES. If the model averages ~2 search queries per prompt (common for grounded answers), 6,000 prompts ≈ 12,000 queries ≈ ~$168/month gross, less whatever the 5,000 free prompts absorb. Budget by QUERIES, not requests; log `usage.grounding_tool_count` to track real burn.
- gemini-2.5-flash: 1,500 grounded requests/DAY free covers your 200/day entirely at $0 grounding cost. Cheapest by a wide margin at this volume, and per-prompt billing is predictable.
Token cost is negligible either way at this volume; grounding fees dominate.


### Rate limit

NOT PUBLISHED as numbers. https://ai.google.dev/gemini-api/docs/rate-limits explicitly declines to table them: "Rate limits depend on a variety of factors (such as your usage tier) and can be viewed in Google AI Studio", directing you to https://aistudio.google.com/rate-limit. I therefore cannot give per-model RPM/TPM/RPD from an official page — read them off your own AI Studio dashboard. LOW confidence on any specific number, and do not hardcode assumptions.
Documented tier ladder: Free ("Active project or free trial"); Tier 1 ("Set up and link an active billing account"); Tier 2 ("Paid $100 + 3 days from first successful payment"); Tier 3 ("Paid $1,000 + 30 days from first successful payment").
Throttling response: "If you hit a spend-based rate limit, the API returns a `429 RESOURCE_EXHAUSTED` error." The docs do NOT document a `Retry-After` header or any quota/ratelimit headers — do not code against one; implement exponential backoff with jitter yourself. Treat the grounding free-tier caps (5,000 prompts/month for Gemini 3; 1,500 RPD for 2.5) as SEPARATE quotas that can 429 you independently of RPM.
At ~200 queries/day your real constraint is the grounding quota, not RPM.


### Trappole

- TERMS-OF-SERVICE RISK — READ FIRST, IT MAY BLOCK THE ENTIRE PRODUCT. https://ai.google.dev/gemini-api/terms 'Grounding with Google Search' prohibits, verbatim: 'You will not ... cache, frame, syndicate, resell, analyze, train on, or otherwise learn from Grounded Results or Search Suggestions', and explicitly names as violations 'using programmatic or automated means to collect Links, using Links to build an index, or using Links to identify destination pages for crawling or scraping'. An AI-visibility monitor that programmatically fires prompts, harvests cited Links and analyzes how often a domain appears sits squarely inside that prohibition. It also requires 'You will only display the Grounded Results with the associated Search Suggestion(s) to the end user who submitted the prompt' — a headless monitoring job has no such end user. Get legal review or written permission from Google before building; at minimum consider storing only aggregate counts. This is a compliance blocker, not a technical one.
- The 30-day figure you may remember concerns GOOGLE's retention, not URL expiry: 'Google will store prompts, contextual information that you may provide, and output for thirty (30) days'. YOUR permitted storage is separately 'up to two (2) years, the text of the Grounded Result(s)' but only (1) to evaluate and optimize the DISPLAY of Grounded Results in your application, or (2) in an end user's chat history so that user can view it. Neither exception cleanly covers longitudinal visibility analytics.
- REDIRECT WRAPPERS are still real on the LEGACY generateContent path. `groundingChunks[].web.uri` is documented with the literal example value 'https://vertexaisearch.cloud.google.com.....' (i.e. /grounding-api-redirect/<token>), and `web.title` is only the bare domain string. There is NO documented `domain` field on the Developer API; `GroundingChunkWeb.domain` exists in client typings but reportedly returns None (googleapis/python-genai issue #1512, still OPEN, priority p3, no official Google answer, last activity Oct 2025).
- THE FIX: use the Interactions API. Its `url_citation.url` is shown in the official example as a direct publisher URL ('https://www.aljazeera.com/sports/euro-2024-final'); the words redirect/vertexaisearch/expire appear nowhere on that page. But the reference describes the field only as 'The URL' — no normative guarantee. ACTION on day one: run one live grounded call and assert `urlparse(u).netloc != 'vertexaisearch.cloud.google.com'` for every citation; keep a redirect-resolver path behind a feature flag in case some models or responses still wrap.
- Redirect EXPIRY is undocumented. No official Google page states a lifetime for grounding-api-redirect URLs. Community reports say they are temporary and stop resolving after a few days. Treat as unknown-and-short: never persist a redirect URL as your durable record of a source. And note that resolving one by following it is exactly the 'programmatic collection of Links' the ToS names.
- BILLING UNIT TRAP on Gemini 3: billed per SEARCH QUERY the model chooses to run, not per API call. One prompt can silently fire 3-5 queries and cost 3-5x. There is no documented parameter to cap the number of searches. Log `usage.grounding_tool_count` on every call and alert on outliers, or your $14/1k becomes far more in practice. Gemini 2.5 is per-prompt and therefore predictable.
- Do NOT install `google-generativeai` — that is the deprecated package. Current is `google-genai` (PyPI 2.15.0, Python >=3.10), imported as `from google import genai`. The Interactions API requires google-genai >= 2.3.0. Your Python 3.12 target is fine.
- The tool key is `google_search` but the SHAPE differs between the two APIs and mixing them fails silently: Interactions uses `{"type": "google_search"}` (typed object), legacy generateContent uses `{"google_search": {}}` (keyed empty object). `google_search_retrieval` is legacy-model-only — do not use it on current models.
- searchEntryPoint.renderedContent (legacy) / the `search_suggestions` HTML in the `google_search_result` step (Interactions) is DISPLAY-REQUIRED by the Terms, max 5 Search Suggestions, and you 'will not modify, or intersperse any other content with, the Grounded Results or Search Suggestions' nor 'place any interstitial content between any Link ... and the associated destination page'. A headless service structurally cannot satisfy this.
- Rate limits are not in the docs at all — only in your AI Studio dashboard. Do not hardcode assumed RPM/RPD. 429 RESOURCE_EXHAUSTED is documented; Retry-After is NOT, so implement your own backoff with jitter.
- For memory-mode (no-search) baseline calls, OMIT the `tools` key entirely rather than sending an empty array. `tools` is documented as optional and no search tool is enabled by default.
- Model IDs have moved on substantially: current stable includes gemini-3.6-flash, gemini-3.5-flash, gemini-3.5-flash-lite, gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite; gemini-3.1-pro-preview is preview. Preview models 'will be deprecated with at least 2 weeks notice' — never pin a preview model in a long-running monitor. Record the exact model id with every datapoint, since grounding behaviour differs across generations and would corrupt your longitudinal comparison.
- Vertex AI is NOT required for grounding — the Developer API with an AI Studio key suffices. Ignore advice telling you to migrate to Vertex just to get grounding.
- Italian-language queries: docs state grounding 'works with all available languages', so no language flag is needed. But results are locale-influenced and there is no documented parameter to pin country/locale (no gl/hl equivalent), so your edunews24.it visibility numbers may drift with the serving locale of your VPS. Record the VPS region as part of your methodology and keep it fixed.


### Fonti consultate

- https://ai.google.dev/gemini-api/docs/interactions/google-search — Interactions API grounding: `tools: [{"type": "google_search"}]`, POST /v1beta/interactions, response steps with url_citation annotations showing DIRECT publisher URLs, search_suggestions, per-search-query billing
- https://ai.google.dev/gemini-api/docs/generate-content/google-search — LEGACY generateContent grounding: `"tools": [{"google_search": {}}]`, full groundingMetadata example with groundingChunks[].web.uri = 'https://vertexaisearch.cloud.google.com.....', web.title, groundingSupports[].segment.startIndex/endIndex, groundingChunkIndices, webSearchQueries, searchEntryPoint.renderedContent
- https://ai.google.dev/api/interactions-api — Interactions API reference: GoogleSearch tool type + search_types enum (web_search|image_search|enterprise_web_search); UrlCitation schema (type/url/title/start_index/end_index, NO domain field); usage fields incl. total_input_tokens, total_output_tokens, total_tokens, grounding_tool_count[]; tools optional
- https://ai.google.dev/gemini-api/docs/interactions-overview — Interactions API GA as of June 2026, 'recommended for all new projects'; generateContent 'now considered legacy' but 'fully supported'; requires google-genai >= 2.3.0; system_instruction parameter; store flag
- https://ai.google.dev/gemini-api/docs/migrate-to-interactions — differences: inline url_citation annotations replace groundingSupports/groundingChunks index mapping; steps[] replaces outputs[]
- https://ai.google.dev/gemini-api/terms — 'Grounding with Google Search' section: display-only-to-the-submitting-end-user requirement, max 5 Search Suggestions, no modification/interstitials, prohibition on cache/analyze/index/scrape and 'using programmatic or automated means to collect Links', Google's 30-day retention, developer's 2-year limited storage exception
- https://ai.google.dev/gemini-api/docs/pricing — grounding: Gemini 3 = 5,000 prompts/month free shared, then $14/1,000 search queries; Gemini 2.5 = 1,500 RPD free then $35/1,000 grounded prompts; token prices per model
- https://ai.google.dev/gemini-api/docs/models — current model IDs (gemini-3.6-flash, gemini-3.5-flash, gemini-3.5-flash-lite, gemini-3.1-pro-preview, gemini-2.5-pro, gemini-2.5-flash, ...) and the preview-deprecation note
- https://ai.google.dev/gemini-api/docs/rate-limits — limits not published, view in AI Studio; tier ladder; 429 RESOURCE_EXHAUSTED
- https://ai.google.dev/gemini-api/docs/changelog — Interactions API launched 2025-12-11; Gemini 3 grounding billing began 2026-01-05; no entry announcing removal of redirect URLs
- https://ai.google.dev/gemini-api/docs/url-context — url_context tool `{"type": "url_context"}`, combinable with google_search, returns url_citation annotations and a url_context_result step
- https://pypi.org/project/google-genai/ — google-genai 2.15.0, Python >=3.10 (current official SDK; google-generativeai is deprecated)
- https://github.com/googleapis/python-genai/issues/1512 — OPEN issue 'Grounding URLs are through vertexaisearch.cloud.google', GroundingChunkWeb.domain returns None, no official resolution (unofficial, used only to flag domain-field unreliability)
- https://firebase.google.com/docs/ai-logic/grounding-google-search — corroborates that groundingChunks contains only uri and title, that uri is a vertexaisearch URL, and that displaying Search Suggestions and sources is required


---

## Anthropic (Claude)

**Confidenza del report: `high`**


Anthropic (Claude) — Messages API server-side web search tool. Verified against platform.claude.com official docs on 2026-07-30.


### Meccanismo di web search

yes — server-side tool executed on Anthropic's infrastructure. You declare `{"type": "web_search_<version>", "name": "web_search"}` in the `tools` array of a normal `POST /v1/messages` call; the API runs the searches inside a server-side agentic loop and returns `server_tool_use` + `web_search_tool_result` blocks plus structured `web_search_result_location` citations attached to text blocks. No beta header (GA). You never execute anything or return a tool_result.


### Modelli

- `claude-opus-5` — search: True — The model used in the official web-search doc examples; 1M context, 128k max output, $5/$25 per MTok. Highest quality for an Italian-language grounded-answer benchmark. Supports all three web_search versions incl. dynamic filtering. Note: `effort` defaults to `high` and adaptive thinking is ON by default on Opus 5 — for a visibility benchmark you likely want `output_config: {"effort": "low"}` (or `"medium"`) plus a fixed setting held constant across all runs so results are comparable.
- `claude-sonnet-5` — search: True — Best cost/quality for ~200 queries/day. $2/$10 per MTok through 2026-08-31 (then $3/$15). 1M context, 128k output, supports dynamic-filtering web search versions (Claude 4.6+ requirement satisfied). This is the pragmatic default for a repeated daily monitoring job.
- `claude-opus-4-8` — search: True — Previous-generation Opus, same $5/$25 pricing, explicitly named in the web-fetch docs as a dynamic-filtering-supported model. Useful as a stable comparison arm or fallback if you want a second Anthropic data point.
- `claude-haiku-4-5` — search: True — Cheapest ($1/$5). CAVEAT: dynamic filtering is documented as 'Claude 4.6 and later models', and Haiku 4.5 predates that — so with web_search_20260209/20260318 you must set `allowed_callers: ["direct"]`, or simply use the basic `web_search_20250305`. Not recommended as the primary arm for a quality benchmark.


### Richiesta

ENDPOINT: POST https://api.anthropic.com/v1/messages
METHOD: POST
AUTH HEADER: `x-api-key: $ANTHROPIC_API_KEY` (NOT Bearer). Also required: `anthropic-version: 2023-06-01` and `content-type: application/json`. NO `anthropic-beta` header — web search is GA.

CURRENT TOOL `type` VERSION STRINGS (all three are current/GA, capability-keyed — newer does NOT deprecate older):
  • `web_search_20260318`  ← LATEST. Dynamic filtering + `response_inclusion` control.
  • `web_search_20260209`  ← dynamic filtering only.
  • `web_search_20250305`  ← basic web search (no dynamic filtering; ZDR-eligible).
The `name` is ALWAYS the literal string `"web_search"`.

MINIMAL COMPLETE BODY (recommended shape for your use case — basic version, direct calls, deterministic block layout):
{
  "model": "claude-sonnet-5",
  "max_tokens": 4096,
  "system": "Rispondi in italiano. Usa la ricerca web per fondare la risposta e cita le fonti.",
  "messages": [
    {"role": "user", "content": "Quali sono le ultime novità sul concorso docenti PNRR3?"}
  ],
  "tools": [
    {
      "type": "web_search_20250305",
      "name": "web_search",
      "max_uses": 5,
      "user_location": {
        "type": "approximate",
        "city": "Roma",
        "region": "Lazio",
        "country": "IT",
        "timezone": "Europe/Rome"
      }
    }
  ]
}

FULL TOOL-DEFINITION FIELD LIST (verbatim from the docs' "Tool definition" JSON):
  "type"              (required) one of the three version strings above
  "name"              (required) "web_search"
  "max_uses"          (optional, int) cap on searches per request. Exceeding → result block is an error with error_code "max_uses_exceeded".
  "allowed_domains"   (optional, string[]) only these domains. Bare domains, NO scheme; optional path, e.g. "example.com" or "example.com/blog". Subdomains auto-included. Wildcards allowed only in the PATH ("example.com/*"), never in the domain ("*.example.com" is invalid).
  "blocked_domains"   (optional, string[]) never these domains.
  ⚠ allowed_domains and blocked_domains are MUTUALLY EXCLUSIVE — sending both returns HTTP 400.
  "user_location"     (optional, object) { "type": "approximate" (must be exactly this), "city", "region", "country" (two-letter ISO 3166-1 alpha-2), "timezone" (IANA tz id) }. At least one of city/region/country/timezone required. Unsupported country codes → 400.
  "allowed_callers"   (optional, string[]) accepts "direct" and/or "code_execution_20260120". DEFAULT DIFFERS BY VERSION: `web_search_20250305` defaults to ["direct"]; `web_search_20260209` and `_20260318` default to ["code_execution_20260120"] (i.e. dynamic filtering ON). Set ["direct"] to disable dynamic filtering (also required for ZDR, and required on models that don't support programmatic tool calling — otherwise you get a 400 telling you to set it).
  "response_inclusion" (optional, `web_search_20260318`+ only) "full" (default) | "excluded". ⚠ SEE GOTCHAS — "excluded" DROPS the result blocks and would break your extraction.
  Plus generic tool properties: "cache_control", "strict", "defer_loading".

SYSTEM PROMPT: passed as the top-level `system` request parameter (a string, or a list of `{"type":"text","text":...}` blocks if you want `cache_control` on it). It is NOT a message with role "system".

OFFICIAL PYTHON SDK EQUIVALENT (`pip install anthropic`):
  import anthropic
  client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY
  response = client.messages.create(
      model="claude-sonnet-5",
      max_tokens=4096,
      system="Rispondi in italiano...",
      messages=[{"role": "user", "content": QUESTION_IT}],
      tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5,
              "user_location": {"type": "approximate", "country": "IT", "timezone": "Europe/Rome"}}],
  )
Async: `anthropic.AsyncAnthropic()` with `await client.messages.create(...)` — appropriate for your FastAPI service. The SDK auto-retries 408/409/429/5xx (default max_retries=2); default timeout 10 minutes (seconds in Python).

MEMORY MODE (identical call, NO tools): simply OMIT the `tools` key entirely (do not send `"tools": []` and do not send `tool_choice`). Everything else — model, system, max_tokens, messages — stays byte-identical so the two arms are comparable:
  response = client.messages.create(
      model="claude-sonnet-5", max_tokens=4096,
      system="Rispondi in italiano...",
      messages=[{"role": "user", "content": QUESTION_IT}],
  )
In memory mode `usage.server_tool_use` will be absent/None and there will be no `citations` arrays. Note the docs state that with no `tools` provided, the tool-use system prompt adds 0 tokens — so token counts also differ between arms, which is expected. (If you ever need tools declared but unusable, `tool_choice: {"type": "none"}` exists, but for a clean memory baseline just omit `tools`.)


### Estrazione delle citazioni

TWO DISTINCT PLACES SOURCES APPEAR — they mean different things and you almost certainly want BOTH:

(A) SOURCES RETRIEVED (the candidate pool the model saw):
  response.content[i].type == "web_search_tool_result"
  response.content[i].tool_use_id                       (pairs with the preceding server_tool_use.id)
  response.content[i].content            → a LIST of result objects, each:
      response.content[i].content[j].type              == "web_search_result"
      response.content[i].content[j].url               ← THE SOURCE URL
      response.content[i].content[j].title
      response.content[i].content[j].page_age          (e.g. "April 30, 2025" — human string, NOT ISO; may be absent)
      response.content[i].content[j].encrypted_content (opaque; must be echoed back verbatim on multi-turn)

(B) SOURCES ACTUALLY CITED IN THE ANSWER TEXT (structured, not markdown):
  response.content[i].type == "text"
  response.content[i].citations               → array (present only on cited text blocks)
  response.content[i].citations[k].type       == "web_search_result_location"   ← EXACT type string
  response.content[i].citations[k].url        ← THE CITED SOURCE URL
  response.content[i].citations[k].title
  response.content[i].citations[k].cited_text (up to 150 chars of the source)
  response.content[i].citations[k].encrypted_index (opaque; echo back on multi-turn)

For an "AI visibility" metric, (B) is the honest answer to "did the answer cite edunews24.it"; (A) is "did edunews24.it even get retrieved". Compute both — the retrieved-but-not-cited delta is itself a useful signal.

The query the model issued: response.content[i].type == "server_tool_use" → .id (prefix "srvtoolu_"), .name == "web_search", .input.query

INLINE / MARKDOWN REFERENCES: there are NONE by design. Anthropic returns citations as structured objects attached to text blocks, not as markdown links or [1]-style brackets in the prose. Do NOT write a markdown-link regex as your primary extractor. (Defensive note: the model can still mention a bare URL in prose if prompted to; treat any such regex as a secondary/diagnostic path only.)

URL FORM: URLs are DIRECT publisher URLs (doc example: "https://en.wikipedia.org/wiki/Claude_Shannon"). They are NOT redirect-wrapped by a tracker/proxy. The real domain is fully recoverable with `urllib.parse.urlparse(url).netloc` — NO HTTP fetch, no HEAD request, no redirect resolution needed. Still normalize before matching: lowercase, strip a leading "www.", and match edunews24.it as a suffix so subdomains count.

NUMBER OF SEARCHES PERFORMED — YES, it is exactly:
  response.usage.server_tool_use.web_search_requests   (integer)
Verified verbatim in both the web-search tool page and the pricing page. This is the billable count. Companion field for the fetch tool is `response.usage.server_tool_use.web_fetch_requests`; for code execution `response.usage.server_tool_use.code_execution_requests`. In memory mode `usage.server_tool_use` is absent — guard with `(response.usage.server_tool_use.web_search_requests if response.usage.server_tool_use else 0)`.

TOKEN USAGE FIELDS: response.usage.input_tokens, response.usage.output_tokens, response.usage.cache_read_input_tokens, response.usage.cache_creation_input_tokens. (Total input = input_tokens + cache_read_input_tokens + cache_creation_input_tokens.)

WITH DYNAMIC FILTERING (`_20260209` / `_20260318` with default allowed_callers): the response ALSO contains code-execution result blocks, and each nested `server_tool_use` / `web_search_tool_result` pair carries an extra `caller` field identifying the code-execution call that made it. Your walker must handle these nested pairs, or you must set `allowed_callers: ["direct"]` to keep the layout flat.


### Prezzi

Observed 2026-07-30 at https://platform.claude.com/docs/en/about-claude/pricing (canonical) and repeated verbatim on the web-search tool page.

SEPARATE PER-SEARCH CHARGE: **$10 per 1,000 searches** on the Claude API (i.e. $0.01 per search), billed IN ADDITION to token costs. Counting unit = `usage.server_tool_use.web_search_requests`. Each web search counts as one use regardless of how many results it returns. If an error occurs during a web search, that search is NOT billed. Batch API web-search calls are priced the same as regular Messages API calls.

WEB FETCH: **no additional charge** — token costs only.

CODE EXECUTION (used internally by dynamic filtering): **free when used with web search or web fetch** — when `web_search_20260209`+ or `web_fetch_20260209`+ is in the request there are no code-execution charges beyond standard tokens. Standalone code execution: 1,550 free hours/org/month, then $0.05/hour/container, 5-minute minimum.

TOKEN PRICES per 1M tokens (input / output), USD:
  claude-fable-5      $10 / $50
  claude-opus-5       $5  / $25
  claude-opus-4-8     $5  / $25
  claude-sonnet-5     $2  / $10  (introductory, through 2026-08-31; then $3 / $15)
  claude-sonnet-4-6   $3  / $15
  claude-haiku-4-5    $1  / $5
Prompt caching multipliers: 5-min cache write 1.25x base input; 1-hour cache write 2x; cache read (hit) 0.1x. Batch API: 50% off input and output.

IMPORTANT COST NOTE FOR YOUR WORKLOAD: web search results become INPUT TOKENS — both across search iterations within a single turn and on every subsequent conversation turn. At ~200 queries/day the per-search fee is small (200 queries x ~3 searches x $0.01 ≈ $6/day at most from search fees) but the retrieved-content input tokens are likely the dominant cost. `max_uses` is your hard cost cap. Dynamic filtering (`_20260318`) exists specifically to cut those input tokens — but it complicates extraction (see gotchas).

BUDGET SANITY CHECK: 200 queries/day x 4 providers, Anthropic arm on claude-sonnet-5 with max_uses=5 → worst case 1,000 searches/day = $10/day in search fees + tokens. On claude-opus-5 the token side roughly doubles.

Exact doc URLs: https://platform.claude.com/docs/en/about-claude/pricing (note: /docs/en/pricing.md returns 404 — the path is /docs/en/about-claude/pricing) and https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool


### Rate limit

Published per usage tier at https://platform.claude.com/docs/en/api/rate-limits (organization-level, per model class, token-bucket replenishment).

START TIER (entry/default; $500/mo spend cap):
  claude-opus-5    1,000 RPM / 2,000,000 ITPM / 400,000 OTPM
  claude-sonnet-5  1,000 RPM / 2,000,000 ITPM / 400,000 OTPM
  claude-haiku-4-5 1,000 RPM / 2,000,000 ITPM / 400,000 OTPM
  claude-fable-5   1,000 RPM /   500,000 ITPM / 100,000 OTPM
BUILD TIER ($1,000/mo cap): opus-5 / sonnet-5 / haiku-4-5 = 5,000 RPM / 5,000,000 ITPM / 1,000,000 OTPM
SCALE TIER ($200,000/mo cap): 10,000 RPM / 10,000,000 ITPM / 2,000,000 OTPM
Note: claude-opus-5 and claude-sonnet-5 each have their OWN bucket. Opus 4.8/4.7/4.6/4.5 share one combined "Opus 4.x" bucket; Sonnet 4.6/4.5 share a "Sonnet 4.x" bucket.
Your ~200 req/day/provider is ~3 orders of magnitude under even Start-tier RPM — rate limits are a non-issue for this workload; only acceleration limits (sharp traffic ramps) could bite.

CACHE-AWARE ITPM: only `input_tokens` + `cache_creation_input_tokens` count toward ITPM. `cache_read_input_tokens` does NOT count (except Claude Haiku 3.5). `max_tokens` does not factor into OTPM.

ON THROTTLING: HTTP **429** with a body describing which limit was exceeded, plus a **`retry-after`** header (seconds). The official SDK reads `retry-after` and retries automatically (default max_retries=2).

RESPONSE HEADERS (present on normal responses too, for headroom monitoring):
  retry-after
  anthropic-ratelimit-requests-limit / -remaining / -reset (RFC 3339)
  anthropic-ratelimit-tokens-limit / -remaining / -reset
  anthropic-ratelimit-input-tokens-limit / -remaining / -reset
  anthropic-ratelimit-output-tokens-limit / -remaining / -reset
  (anthropic-priority-* variants for Priority Tier; anthropic-fast-* for fast mode)
In Python, read them via `client.messages.with_raw_response.create(...)` → `.headers`, then `.parse()` for the Message.

SEPARATE WEB SEARCH RATE LIMIT: yes, one exists but the numeric value is NOT published in the docs — the Batches API "throttles web search requests per organization" and the docs direct you to your org's web search rate limit on the Console **Limits** page (/settings/limits). Also, hitting it inside a turn does NOT raise — it surfaces as a `web_search_tool_result` error with `error_code: "too_many_requests"` inside an HTTP 200 response.

Managed Agents endpoints (not used here) have separate limits: 300 RPM create / 1,200 RPM read.


### Trappole

- VERSION STRING IS NEWER THAN MOST CACHED KNOWLEDGE. As of 2026-07-30 the latest is `web_search_20260318` (adds `response_inclusion`), then `web_search_20260209` (dynamic filtering), then `web_search_20250305` (basic). All three are simultaneously GA — this is 'capability-keyed' versioning, not deprecation. If you had `web_search_20250305` hardcoded it still works; it is not stale.
- ⚠ PRODUCT-KILLING FLAG: on `web_search_20260318`, setting `"response_inclusion": "excluded"` DROPS the nested `server_tool_use` + `web_search_tool_result` block pairs from the response entirely (when consumed by a completed code-execution call). Your source list would silently vanish. Default is `"full"` — never set `"excluded"` for this product. Leave it unset.
- ⚠ DYNAMIC FILTERING CHANGES THE RESPONSE SHAPE. On `_20260209`/`_20260318` the default is `allowed_callers: ["code_execution_20260120"]`, so searches run INSIDE code execution: the response additionally contains code-execution result blocks, and each nested `server_tool_use`/`web_search_tool_result` pair carries an extra `caller` field. STRONG RECOMMENDATION for a measurement tool: either use `web_search_20250305`, or set `"allowed_callers": ["direct"]` on the newer version. That gives you a flat, predictable, stable block layout AND makes the tool ZDR-eligible. Trade-off: you lose the token savings of dynamic filtering.
- ⚠ SEARCH ERRORS RETURN HTTP 200, NOT AN EXCEPTION. On error the `web_search_tool_result.content` is a single OBJECT `{"type": "web_search_tool_result_error", "error_code": "..."}` instead of a LIST of results. Your extractor MUST branch on `isinstance(block.content, list)` (or check `content.type`) before iterating — otherwise you'll crash or silently record zero sources. Error codes: too_many_requests, invalid_tool_input, max_uses_exceeded, query_too_long, request_too_large, unavailable. A successful search with no hits returns an EMPTY LIST, which is semantically different from an error — record the two distinctly or you'll pollute your visibility metric.
- ⚠ `pause_turn` IS MANDATORY TO HANDLE, and streaming does NOT solve it. Long server-side search loops return `stop_reason: "pause_turn"` with a partial answer. You MUST re-send: append `{"role":"assistant","content": response.content}` to messages and call again WITH THE SAME `tools` ARRAY (a continuation missing the tool returns a validation error). A continued turn can pause again — loop with a cap (e.g. 5). If you don't handle this you will systematically under-count citations on exactly the research-heavy Italian queries you care most about.
- STREAMING IS NOT REQUIRED for long calls — `pause_turn` is the mechanism, and the Python SDK's default timeout is 10 minutes. Practical rule: streaming is only needed to avoid HTTP timeouts at large `max_tokens` (roughly >16k non-streaming). At `max_tokens: 4096` for a benchmark answer, plain non-streaming `.create()` is correct and simpler. If you do raise max_tokens, use `client.messages.stream(...)` + `.get_final_message()`.
- A `server_tool_use` BLOCK WITHOUT A MATCHING RESULT BLOCK means the search hasn't run. This happens when Claude calls a server tool and a client tool in the same parallel group: `stop_reason` is `"tool_use"` (NOT pause_turn) and the search is deferred until you return the client tool_result. You have no client tools, so this shouldn't occur — but pair result blocks by `tool_use_id`, never by array position, since in that flow the pair is split across two responses.
- MULTI-TURN: `encrypted_content` (on results) and `encrypted_index` (on citations) MUST be echoed back byte-identical if you continue the conversation. Modified or missing → HTTP 400 validation error. For your one-shot-per-question design this is moot, but do not strip these fields if you ever add follow-ups.
- `page_age` IS A HUMAN-READABLE STRING ("April 30, 2025"), not ISO-8601, and may be absent. Parse defensively with dateutil and tolerate None — do not build a required schema field on it.
- WEB SEARCH CAN BE DISABLED ORG-WIDE. An admin can turn it off (or restrict searchable domains) in the Console at /settings/privacy. If disabled, a request including the tool fails with HTTP 400 `invalid_request_error` saying web search is not enabled — this is a hard failure at request level, NOT an error code inside a result block. Verify with one live call before your first production run.
- REQUEST-LEVEL `allowed_domains` MUST BE A SUBSET of any org-level allowlist, or you get a validation error; org-blocked domains are silently stripped from your allowlist rather than erroring. Relevant if you ever scope searches to Italian education domains.
- HOMOGRAPH RISK IN DOMAIN MATCHING: the docs warn that Unicode lookalikes (Cyrillic 'а' in 'аmazon.com') can bypass domain filters. For edunews24.it matching, normalize with IDNA and reject non-ASCII netlocs, or you could record a false positive from a lookalike domain.
- MEASUREMENT-VALIDITY GOTCHA (not an API bug): search triggering is model-discretionary — 'Claude searches when the request depends on information that is current, changing, or outside its training data' and answers directly otherwise. So a zero-search turn is a legitimate outcome, not a failure. Log `web_search_requests == 0` as its own category. Triggering is steerable via the system prompt and hard-capped via `max_uses`; keep the system prompt BYTE-IDENTICAL across all runs and providers or your longitudinal series is not comparable.
- `user_location` MATTERS for an Italian-language monitor — set `{"type":"approximate","country":"IT","timezone":"Europe/Rome"}` (plus city/region if you want) so results are localized to Italy. Omitting it may skew toward non-Italian sources and depress edunews24.it visibility for reasons unrelated to actual ranking. `type` must be exactly `"approximate"`; an unsupported country code returns 400.
- PROVIDER-COMPARABILITY: citation counts are not apples-to-apples across providers. Anthropic exposes BOTH the retrieved set (`web_search_tool_result.content[].url`) and the cited subset (`citations[].url`). Other providers often expose only one. Decide up front which is your metric and store both, or your cross-provider chart is meaningless.
- COST OF NOT CACHING: the tool definition and system prompt are identical on every one of your ~200 daily calls. Put `cache_control: {"type": "ephemeral"}` on the last system text block to cache tools+system together (render order is tools → system → messages). Minimum cacheable prefix is 512 tokens on claude-opus-5, 1024 on claude-sonnet-5/opus-4-8 — a short Italian system prompt may fall below the threshold and silently not cache (`cache_creation_input_tokens: 0`, no error).
- DOCS ARE CIRCULAR ON THE PER-MODEL SUPPORT MATRIX: the web-search page says 'For model support, see the Tool reference', and the Tool reference says 'For model compatibility, see each tool's page' — and neither has a per-model column for web search. What IS stated explicitly: dynamic filtering requires 'Claude 4.6 and later models'; the doc examples use claude-opus-5. Query the Models API (`GET /v1/models/{id}` → `capabilities`) if you need a machine-checkable per-model answer.
- PLATFORM AVAILABILITY: web search is available on the Claude API, Claude Platform on AWS, and Microsoft Foundry (Hosted-on-Anthropic deployments only). On Google Cloud ONLY the basic `web_search_20250305` is available. It is NOT available on Amazon Bedrock at all. Irrelevant if you use the first-party API with your own key, but fatal if you ever move the Anthropic arm to Bedrock.
- `cited_text`, `title`, and `url` inside citation objects do NOT count toward input or output token usage — a small pricing nicety worth knowing when you reconcile your cost model against invoices.


### Fonti consultate

- https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool — tool versions (web_search_20260318 / _20260209 / _20250305), full tool definition, response block shapes, web_search_result fields, web_search_result_location citation object, usage.server_tool_use.web_search_requests, $10/1,000 searches, error codes, pause_turn, streaming SSE example
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool — web fetch tool exists: web_fetch_20260318 / _20260309 / _20260209 / _20250910; tool definition (max_uses, allowed_domains, blocked_domains, citations, max_content_tokens, use_cache, response_inclusion); web_fetch_tool_result / web_fetch_result / document block; usage.server_tool_use.web_fetch_requests; no additional cost; URL-must-be-in-prior-context restriction
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-reference — canonical Anthropic-provided tool `type` table and GA status; tool versioning semantics (capability-keyed vs model-keyed); allowed_callers values
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/server-tools — server_tool_use block and srvtoolu_ id prefix; server-side loop and pause_turn continuation code; mixing server+client tools (stop_reason tool_use); ZDR and allowed_callers; domain filtering rules and homograph warning; dynamic filtering with code execution; batch behavior
- https://platform.claude.com/docs/en/about-claude/pricing — model token pricing, web search $10/1,000 searches, web fetch no additional cost, code execution free with web search/fetch, prompt caching multipliers, batch discount (NOTE: /docs/en/pricing.md 404s; this is the correct path)
- https://platform.claude.com/docs/en/api/rate-limits — Start/Build/Scale tier RPM/ITPM/OTPM per model, 429 + retry-after, full anthropic-ratelimit-* header list, cache-aware ITPM, separate per-model buckets for Opus 5 and Sonnet 5
- https://platform.claude.com/docs/en/about-claude/models/overview — exact current model IDs (claude-opus-5, claude-sonnet-5, claude-haiku-4-5, claude-opus-4-8, claude-fable-5), context windows, max output, effort defaults
