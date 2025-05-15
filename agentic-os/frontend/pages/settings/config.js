// pages/settings/config.js

import { useState, useEffect, useCallback, useMemo } from "react";
import Header from "../../components/Header";

// In‐page toast message
function MessageBar({ type, text, onClose }) {
  if (!text) return null;
  const bg = type === "error" ? "bg-red-100 text-red-800" : "bg-green-100 text-green-800";
  return (
    <div className={`${bg} p-3 rounded mb-4 flex justify-between items-center`}>
      <span>{text}</span>
      <button onClick={onClose} className="font-bold">✕</button>
    </div>
  );
}

// Guess field type by key/value
function guessFieldType(key, val) {
  if (Array.isArray(val)) return "list";
  if (typeof val === "boolean" || val === "true" || val === "false") return "boolean";
  if (!isNaN(val) && val !== "" && val !== true && val !== false) return "number";
  if (typeof val === "string" && val.startsWith("http")) return "url";
  if (key.match(/_PATH$/) || (typeof val === "string" && val.includes("/"))) return "path";
  if (key.match(/TOKEN|SECRET|KEY/)) return "password";
  if (key.match(/MODE|LEVEL|TYPE|INTERACTIVE/i)) return "enum";
  return "string";
}

// Known enums; extend as needed
const ENUM_OPTIONS = {
  LOG_LEVEL: ["TRACE","DEBUG","INFO","WARN","ERROR"],
  ENABLE_TRACING: ["true","false"],
  INTERACTIVE_MODE: ["timer","manual"],
  LLM_REASONING_LEVEL: ["low","medium","high"],
};

// Editable list with reorder support
function EditableListField({ value, onChange }) {
  const [draft, setDraft] = useState("");
  const list = Array.isArray(value) ? value : [];

  const addItem = () => {
    const v = draft.trim();
    if (v) {
      onChange([...list, v]);
      setDraft("");
    }
  };

  const removeAt = idx => {
    onChange(list.filter((_, i) => i !== idx));
  };

  const moveItem = (from, to) => {
    if (to < 0 || to >= list.length) return;
    const cp = [...list];
    const [item] = cp.splice(from, 1);
    cp.splice(to, 0, item);
    onChange(cp);
  };

  return (
    <div>
      <ul className="mb-2">
        {list.map((item, i) => (
          <li key={i} className="flex items-center space-x-2 mb-1">
            <button
              type="button"
              onClick={() => moveItem(i, i - 1)}
              disabled={i === 0}
              className="text-gray-500 hover:text-gray-700"
              title="Move up"
            >↑</button>
            <button
              type="button"
              onClick={() => moveItem(i, i + 1)}
              disabled={i === list.length - 1}
              className="text-gray-500 hover:text-gray-700"
              title="Move down"
            >↓</button>
            <input
              className="flex-1 border px-2 py-1 rounded"
              value={item}
              onChange={e => {
                const cp = [...list];
                cp[i] = e.target.value;
                onChange(cp);
              }}
            />
            <button
              type="button"
              onClick={() => removeAt(i)}
              className="text-red-600 font-bold px-1"
              title="Remove"
            >×</button>
          </li>
        ))}
      </ul>
      <div className="flex">
        <input
          className="flex-1 border px-2 py-1 rounded mr-2"
          placeholder="Add new item…"
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Enter") {
              e.preventDefault();
              addItem();
            }
          }}
        />
        <button
          type="button"
          onClick={addItem}
          className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded"
        >Add</button>
      </div>
    </div>
  );
}

// Renders appropriate input widget
function RenderField({ fieldKey, value, onChange, modelList }) {
  // Special dropdown for LLM_MODEL
  if (fieldKey === "LLM_MODEL" && modelList.length > 0) {
    return (
      <select
        value={value || ""}
        onChange={e => onChange(fieldKey, e.target.value)}
        className="w-full border p-2 rounded"
      >
        {modelList.map(m => (
          <option key={m.id || m.model_name} value={m.model_name}>
            {m.model_name}
          </option>
        ))}
      </select>
    );
  }

  const type = guessFieldType(fieldKey, value);

  if (type === "enum" && ENUM_OPTIONS[fieldKey]) {
    return (
      <select
        value={value}
        onChange={e => onChange(fieldKey, e.target.value)}
        className="w-full border p-2 rounded"
      >
        {ENUM_OPTIONS[fieldKey].map(opt => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    );
  }
  if (type === "boolean") {
    return (
      <select
        value={String(value)}
        onChange={e => onChange(fieldKey, e.target.value === "true")}
        className="w-full border p-2 rounded"
      >
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    );
  }
  if (type === "number") {
    return (
      <input
        type="number"
        value={value}
        onChange={e => onChange(fieldKey, e.target.value)}
        className="w-full border p-2 rounded"
      />
    );
  }
  if (type === "url") {
    return (
      <input
        type="url"
        value={value}
        onChange={e => onChange(fieldKey, e.target.value)}
        className="w-full border p-2 rounded"
      />
    );
  }
  if (type === "password") {
    return (
      <input
        type="password"
        value={value}
        onChange={e => onChange(fieldKey, e.target.value)}
        className="w-full border p-2 rounded"
      />
    );
  }
  if (type === "list") {
    return <EditableListField value={value} onChange={val => onChange(fieldKey, val)} />;
  }
  // Fallback: text/path
  return (
    <input
      type="text"
      value={value === null ? "" : value}
      onChange={e => onChange(fieldKey, e.target.value)}
      className="w-full border p-2 rounded font-mono"
    />
  );
}

// Hook to load, track dirty state, save/reset one scope
function useConfig(scope) {
  const [cfg, setCfg] = useState(null);
  const [orig, setOrig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const fetchCfg = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`/api/config/list?scope=${encodeURIComponent(scope)}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setCfg(data);
      setOrig(data);
    } catch (e) {
      setError("Load failed: " + e.message);
    } finally {
      setLoading(false);
    }
  }, [scope]);

  useEffect(() => {
    if (scope) fetchCfg();
  }, [scope, fetchCfg]);

  const dirty = useMemo(() => {
    if (!cfg || !orig) return false;
    const keys = new Set([...Object.keys(cfg), ...Object.keys(orig)]);
    for (let k of keys) {
      const a = cfg[k], b = orig[k];
      if (Array.isArray(a) || Array.isArray(b)) {
        if (JSON.stringify(a || []) !== JSON.stringify(b || [])) return true;
      } else if (String(a) !== String(b)) return true;
    }
    return false;
  }, [cfg, orig]);

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      const items = {};
      for (let k in cfg) {
        let v = cfg[k];
        if (Array.isArray(v)) items[k] = v;
        else if (typeof v === "boolean") items[k] = String(v);
        else items[k] = v;
      }
      const res = await fetch("/api/config/bulk_set", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope, items }),
      });
      if (!res.ok) throw new Error(await res.text());
      setOrig(cfg);
      return true;
    } catch (e) {
      setError("Save failed: " + e.message);
      return false;
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    setCfg(orig);
    setError("");
  };

  return { cfg, setCfg, loading, saving, error, dirty, fetchCfg, save, reset };
}

export default function SettingsPage() {
  const [scopes, setScopes] = useState([]);
  const [active, setActive] = useState("");
  const [msg, setMsg] = useState({ type: "", text: "" });
  const [modelList, setModelList] = useState([]);

  // Load scope tabs
  useEffect(() => {
    fetch("/api/config/scopes")
      .then(r => r.json())
      .then(list => {
        if (!Array.isArray(list)) list = [];
        const tabs = list.filter(s => s === "global" || s.startsWith("service."));
        setScopes(tabs);
        setActive(tabs[0] || "");
      });
  }, []);

  // Load available models
  useEffect(() => {
    fetch("/api/models")
      .then(r => r.json())
      .then(d => setModelList(d.models || []))
      .catch(() => setModelList([]));
  }, []);

  const {
    cfg, setCfg, loading, saving,
    error, dirty, fetchCfg, save, reset
  } = useConfig(active);

  const onChangeField = (key, val) => setCfg(c => ({ ...c, [key]: val }));

  const onSave = async () => {
    const ok = await save();
    if (ok) setMsg({ type: "success", text: "Saved successfully" });
  };
  const onReset = () => {
    reset();
    setMsg({ type: "", text: "" });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Settings"
        breadcrumbs={[
          { href: "/", label: "Home" },
          { href: "/settings", label: "Settings" },
          { href: "/settings/config", label: "Config" },
        ]}
      />
      <main className="max-w-6xl mx-auto py-8 px-4">
        <div className="bg-white shadow rounded-lg">
          {/* Tabs */}
          <div className="border-b">
            <nav className="flex space-x-4 px-4">
              {scopes.map(s => (
                <button
                  key={s}
                  onClick={() => { setActive(s); setMsg({}); }}
                  className={
                    "py-3 px-1 border-b-2 text-sm font-medium " +
                    (s === active
                      ? "border-blue-500 text-blue-600"
                      : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700")
                  }
                >
                  {s === "global" ? "global" : s.replace(/^service\./, "")}
                </button>
              ))}
            </nav>
          </div>

          {/* Content */}
          <div className="p-6">
            <MessageBar type={msg.type} text={msg.text} onClose={() => setMsg({})} />
            {error && <MessageBar type="error" text={error} onClose={() => {}} />}

            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">
                {active === "global" ? "global" : active.replace(/^service\./, "")}
              </h2>
              <button
                onClick={fetchCfg}
                disabled={loading}
                className="text-sm text-gray-600 hover:text-gray-800"
              >⟳ Refresh</button>
            </div>

            {loading || !cfg ? (
              <div>Loading…</div>
            ) : Object.keys(cfg).length === 0 ? (
              <div className="text-gray-400">No settings in this scope.</div>
            ) : (
              <div className="space-y-4">
                {Object.entries(cfg).map(([k, v]) => (
                  <div key={k}>
                    <label className="block text-gray-700 mb-1">{k}</label>
                    <RenderField
                      fieldKey={k}
                      value={v}
                      onChange={onChangeField}
                      modelList={modelList}
                    />
                  </div>
                ))}
              </div>
            )}

            {/* Actions */}
            <div className="flex space-x-4 mt-6">
              <button
                onClick={onSave}
                disabled={!dirty || saving}
                className={
                  "px-5 py-2 rounded text-white transition " +
                  (dirty && !saving
                    ? "bg-blue-600 hover:bg-blue-700"
                    : "bg-gray-400 cursor-not-allowed")
                }
              >
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                onClick={onReset}
                disabled={!dirty || loading}
                className={
                  "px-5 py-2 rounded text-white transition " +
                  (dirty
                    ? "bg-gray-600 hover:bg-gray-700"
                    : "bg-gray-300 cursor-not-allowed")
                }
              >
                Reset
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
