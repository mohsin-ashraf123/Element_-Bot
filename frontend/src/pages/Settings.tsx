import { useCallback, useEffect, useMemo, useState } from "react";

import clsx from "clsx";

import { Icon } from "../components/Icon";

import { Switch } from "../components/ui/Switch";

import { useTheme } from "../lib/theme";

import { useAuth } from "../lib/auth";

import {

  fetchOpenRouterModels,

  getSettings,

  updateSettings,

  type OpenRouterModel,

} from "../lib/api";



type Provider = "anthropic" | "openai" | "gemini" | "openrouter";



export function Settings() {

  const { toggle } = useTheme();

  const { user, logout } = useAuth();

  const [provider, setProvider] = useState<Provider>("openrouter");

  const [freeOnly, setFreeOnly] = useState(false);

  const [search, setSearch] = useState("");

  const [apiKey, setApiKey] = useState("");

  const [models, setModels] = useState<OpenRouterModel[]>([]);

  const [fetchError, setFetchError] = useState<string | null>(null);

  const [fetched, setFetched] = useState(false);

  const [loading, setLoading] = useState(false);

  const [chosen, setChosen] = useState<string | null>(null);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [keySaved, setKeySaved] = useState(false);
  const [saving, setSaving] = useState(false);



  const isOR = provider === "openrouter";



  useEffect(() => {

    getSettings()

      .then((s) => {

        const p = (s.llm?.provider as Provider) || "openrouter";

        setProvider(p);

        if (s.llm?.model) setChosen(s.llm.model);
        if (typeof s.llm?.enabled === "boolean") setAiEnabled(s.llm.enabled);
        if (s.llm?.api_key_set) setKeySaved(true);

      })

      .catch(() => undefined);

  }, []);



  const loadModels = useCallback(async () => {
    if (!apiKey.trim()) {
      setFetchError("Paste your OpenRouter API key first, then tap Fetch");
      return;
    }
    setLoading(true);
    setFetchError(null);
    try {
      const res = await fetchOpenRouterModels({
        api_key: apiKey.trim(),
        free_only: freeOnly,
      });

      if (res.error) {
        setFetchError(res.error);
        setModels([]);
      } else {
        setModels(res.models);
        setFetched(true);
        await updateSettings("llm", {
          provider: "openrouter",
          enabled: aiEnabled,
          pseudonymise: false,
          model: chosen,
          api_key: apiKey.trim(),
        });
        setKeySaved(true);
      }
    } catch {
      setFetchError("Could not load models — check your connection");
      setModels([]);
    } finally {
      setLoading(false);
    }
  }, [apiKey, freeOnly, aiEnabled, chosen]);



  const visible = useMemo(() => {

    const q = search.trim().toLowerCase();

    if (!q) return models;

    return models.filter(

      (m) => m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q)

    );

  }, [models, search]);



  const selectModel = async (id: string) => {
    setChosen(id);
    setSaving(true);
    try {
      await updateSettings("llm", {
        provider: "openrouter",
        enabled: aiEnabled,
        pseudonymise: false,
        model: id,
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
      });
      if (apiKey.trim()) setKeySaved(true);
    } finally {
      setSaving(false);
    }
  };

  const saveLlmKey = async () => {
    if (!apiKey.trim()) return;
    setSaving(true);
    try {
      await updateSettings("llm", {
        provider: "openrouter",
        enabled: aiEnabled,
        pseudonymise: false,
        model: chosen,
        api_key: apiKey.trim(),
      });
      setKeySaved(true);
    } finally {
      setSaving(false);
    }
  };



  return (

    <div className="grid g2">

      <div className="card reveal">

        <div className="cap">

          <Icon name="gear" size={16} style={{ color: "var(--accent)" }} />

          LLM narratives

        </div>

        <div className="field">

          <div>

            <div className="fl">Provider</div>

            <div className="fd">Used only for report summaries</div>

          </div>

          <div className="pillbtns">

            {(["anthropic", "openai", "gemini", "openrouter"] as Provider[]).map((p) => (

              <button

                key={p}

                className={clsx("pillbtn", provider === p && "on")}

                onClick={() => setProvider(p)}

                type="button"

              >

                {p === "openrouter" ? "OpenRouter" : p[0].toUpperCase() + p.slice(1)}

              </button>

            ))}

          </div>

        </div>



        {!isOR && (

          <div className="field">

            <div style={{ flex: 1 }}>

              <div className="fl">API key</div>

              <div className="fd">Encrypted at rest · never shown in plain text</div>

            </div>

            <input className="inp" placeholder="Paste key…" style={{ maxWidth: 190, margin: 0 }} />

          </div>

        )}



        {isOR && !keySaved ? (
          <div className="auth-error" style={{ marginBottom: 12 }}>
            <Icon name="warn" size={14} />
            API key not saved yet — paste your sk-or-… key and tap <b>Fetch</b> or <b>Save key</b>
            before generating AI reports.
          </div>
        ) : null}

        {isOR && (

          <div style={{ marginTop: 4 }}>

            <div className="field">

              <div style={{ flex: 1 }}>

                <div className="fl">OpenRouter key</div>

                <div className="fd">
                  Paste key or use LLM_API_KEY from .env
                  {keySaved ? " · key saved" : ""}
                </div>

              </div>

              <div style={{ display: "flex", gap: 8, alignItems: "center", margin: 0 }}>

                <input

                  className="inp"

                  placeholder="sk-or-…"

                  style={{ maxWidth: 150, margin: 0 }}

                  value={apiKey}

                  onChange={(e) => setApiKey(e.target.value)}

                  type="password"

                  autoComplete="off"

                />

                <button
                  className="btn ghost"
                  style={{ padding: "9px 13px" }}
                  onClick={saveLlmKey}
                  type="button"
                  disabled={saving || !apiKey.trim()}
                >
                  Save key
                </button>
                <button

                  className="btn primary"

                  style={{ padding: "9px 13px" }}

                  onClick={loadModels}

                  type="button"

                  disabled={loading}

                >

                  {loading ? "Loading…" : "Fetch"}

                </button>

              </div>

            </div>



            <div className="field">

              <div style={{ flex: 1 }}>

                <div className="fl">Search models</div>

                <div className="fd">Filter by name or model id</div>

              </div>

              <input

                className="inp"

                placeholder="e.g. llama, claude, gemma…"

                style={{ maxWidth: 220, margin: 0 }}

                value={search}

                onChange={(e) => setSearch(e.target.value)}

                onKeyDown={(e) => e.key === "Enter" && loadModels()}

              />

            </div>



            <div className="field">

              <div>

                <div className="fl">Free models only</div>

                <div className="fd">Filter out paid models</div>

              </div>

              <Switch defaultOn={false} onChange={setFreeOnly} />

            </div>



            <div style={{ padding: "6px 4px 2px" }}>

              <div className="inp-lbl">

                Available models{" "}

                {fetched && (

                  <span style={{ color: "var(--text3)" }}>

                    · {visible.length} shown

                    {search.trim() ? ` (of ${models.length})` : ""}

                  </span>

                )}

              </div>



              {fetchError && (

                <div className="auth-error" style={{ marginBottom: 10 }}>

                  <Icon name="warn" size={14} />

                  {fetchError}

                </div>

              )}



              <div className="model-list">

                {!fetched ? (

                  <div

                    style={{

                      color: "var(--text3)",

                      fontSize: 12.5,

                      fontWeight: 500,

                      padding: "10px 2px",

                    }}

                  >

                    Paste your key (or set LLM_API_KEY in .env) and tap Fetch.

                  </div>

                ) : visible.length === 0 ? (

                  <div

                    style={{

                      color: "var(--text3)",

                      fontSize: 12.5,

                      fontWeight: 500,

                      padding: "10px 2px",

                    }}

                  >

                    No models match your filters.

                  </div>

                ) : (

                  visible.map((m) => (

                    <div

                      key={m.id}

                      className={clsx("model-row", chosen === m.id && "sel")}

                      onClick={() => selectModel(m.id)}

                      role="button"

                      tabIndex={0}

                      onKeyDown={(e) => e.key === "Enter" && selectModel(m.id)}

                    >

                      <div className="radio" />

                      <div style={{ minWidth: 0, flex: 1 }}>

                        <div className="mn">{m.name}</div>

                        <div className="mm">{m.id}</div>

                      </div>

                      <span className={m.free ? "free-tag" : "paid-tag"}>

                        {m.free ? "FREE" : "paid"}

                      </span>

                    </div>

                  ))

                )}

              </div>



              {chosen && (

                <div

                  style={{

                    fontSize: 12.5,

                    fontWeight: 560,

                    color: "var(--accent)",

                    padding: "8px 2px",

                  }}

                >

                  {saving ? "Saving…" : `✓ Selected: ${chosen}`}

                </div>

              )}

            </div>

          </div>

        )}



        <div className="field">

          <div>

            <div className="fl">Enable AI summaries</div>

            <div className="fd">Off = deterministic templates only</div>

          </div>

          <Switch
            defaultOn={aiEnabled}
            onChange={async (on) => {
              setAiEnabled(on);
              await updateSettings("llm", {
                provider: "openrouter",
                enabled: on,
                pseudonymise: false,
                model: chosen,
              });
            }}
          />

        </div>

      </div>



      <div className="card reveal">

        <div className="cap">

          <Icon name="shield" size={16} style={{ color: "var(--accent)" }} />

          Account &amp; appearance

        </div>

        <div className="field">

          <div>

            <div className="fl">Admin</div>

            <div className="fd">{user ?? "—"}</div>

          </div>

          <button className="btn ghost" style={{ padding: "7px 12px" }} type="button" onClick={logout}>

            Sign out

          </button>

        </div>

        <div className="field">

          <div>

            <div className="fl">Appearance</div>

            <div className="fd">Light / Dark</div>

          </div>

          <button className="btn ghost" style={{ padding: "7px 12px" }} type="button" onClick={toggle}>

            Toggle

          </button>

        </div>

      </div>

    </div>

  );

}

