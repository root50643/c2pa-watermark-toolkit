import { KeyRound, LogOut, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import type { MessageKey } from "../i18n";
import type { Customer } from "../types";

interface ConnectionPanelProps {
  customer: Customer | null;
  loading: boolean;
  onConnect: (key: string) => Promise<void>;
  onDisconnect: () => void;
  t: (key: MessageKey) => string;
}

export function ConnectionPanel({ customer, loading, onConnect, onDisconnect, t }: ConnectionPanelProps) {
  const [key, setKey] = useState("");
  const [visible, setVisible] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!key.trim()) return;
    await onConnect(key.trim());
    setKey("");
  };

  if (customer) {
    return (
      <section className="connection connected-card">
        <div className="customer-badge" aria-hidden="true">
          <ShieldCheck size={22} />
        </div>
        <div className="customer-copy">
          <span>{t("connectedAs")}</span>
          <strong>{customer.customer_name}</strong>
          <small>{t("keyPrefix")}: {customer.key_prefix}</small>
        </div>
        <button className="button ghost compact" type="button" onClick={onDisconnect}>
          <LogOut size={16} />
          {t("disconnect")}
        </button>
      </section>
    );
  }

  return (
    <section className="connection connect-card">
      <div className="connect-heading">
        <div className="connection-mark" aria-hidden="true"><KeyRound size={24} /></div>
        <div>
          <span className="eyebrow">RAIW API</span>
          <h2>{t("connectTitle")}</h2>
          <p>{t("connectDescription")}</p>
        </div>
      </div>
      <form className="key-form" onSubmit={submit}>
        <label htmlFor="api-key">{t("apiKey")}</label>
        <div className="key-input-row">
          <input
            id="api-key"
            type={visible ? "text" : "password"}
            autoComplete="off"
            spellCheck="false"
            value={key}
            placeholder={t("apiKeyPlaceholder")}
            onChange={(event) => setKey(event.target.value)}
          />
          <button className="text-button" type="button" onClick={() => setVisible((current) => !current)}>
            {visible ? "•••" : "Aa"}
          </button>
          <button className="button primary" type="submit" disabled={!key.trim() || loading}>
            {loading ? t("connecting") : t("connect")}
          </button>
        </div>
        <small>{t("sessionKeyHint")}</small>
      </form>
    </section>
  );
}
