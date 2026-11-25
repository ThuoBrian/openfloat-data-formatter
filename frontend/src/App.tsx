/**
 * The page shell: header, the mode choice, the sidebar, and closing the app.
 * Wording is aimed at non-technical staff.
 */
import { useEffect, useRef, useState } from "react";

import { getSettings, shutDown, type UiDefaults } from "./api/client";
import { ErrorNotice, Notice } from "./components/ui";
import { StatementPage } from "./pages/StatementPage";
import { TransformPage } from "./pages/TransformPage";

const MODES = [
  {
    id: "transform",
    label: "Prepare an OpenFloat upload",
    caption: "Turn a Process Maker export into a file OpenFloat accepts.",
  },
  {
    id: "statement",
    label: "Check payment results",
    caption: "After a disbursement: see who was paid and who wasn't.",
  },
] as const;
type Mode = (typeof MODES)[number]["id"];

/** A country code: 1-3 digits (config.COUNTRY_PREFIX_PATTERN). */
const COUNTRY_PREFIX = /^\d{1,3}$/;

const MODE_KEY = "openfloat.mode";

export function App() {
  const [defaults, setDefaults] = useState<UiDefaults | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [closed, setClosed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getSettings(controller.signal)
      .then(setDefaults)
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setLoadError(caught);
      });
    return () => controller.abort();
  }, []);

  return (
    <div className="shell">
      <header className="header">
        <div>
          <h1>OpenFloat Data Formatter</h1>
          <p>Airtime disbursement files for OpenFloat, checked before you upload and reconciled after.</p>
        </div>
        <span className="badge">Files stay on this computer</span>
      </header>

      {closed ? (
        <main className="main">
          <Notice tone="success">
            <p>
              <strong>The app has closed.</strong> You can close this browser tab now. To use it
              again, open the <strong>OpenFloat Data Formatter</strong> shortcut.
            </p>
          </Notice>
        </main>
      ) : loadError !== null ? (
        <main className="main">
          <ErrorNotice
            message="The app isn't responding. Close this tab, then open the OpenFloat Data Formatter shortcut again."
            error={loadError}
          />
        </main>
      ) : defaults === null ? (
        <main className="main">
          <p className="muted" role="status">Starting…</p>
        </main>
      ) : (
        <Workspace defaults={defaults} onClosed={() => setClosed(true)} />
      )}
    </div>
  );
}

function Workspace({ defaults, onClosed }: { defaults: UiDefaults; onClosed: () => void }) {
  const [mode, setMode] = useState<Mode>(readMode);
  const [countryPrefix, setCountryPrefix] = useState(defaults.default_country_prefix);
  const [threshold, setThreshold] = useState(String(defaults.max_amount_threshold));
  // Bumped by "Start over": remounting the page empties every upload and choice.
  const [round, setRound] = useState(0);

  const prefix = countryPrefix.trim();
  const prefixValid = COUNTRY_PREFIX.test(prefix);
  const thresholdValue = Number(threshold);
  const thresholdValid = threshold.trim() !== "" && Number.isInteger(thresholdValue) && thresholdValue >= 0;

  function chooseMode(next: Mode) {
    setMode(next);
    try {
      localStorage.setItem(MODE_KEY, next); // a convenience only; never file contents
    } catch {
      // Storage blocked: the page still works, it just won't remember.
    }
  }

  return (
    <div className="workspace">
      <aside className="sidebar" aria-label="Help and settings">
        <h2 className="sidebar-heading">How it works</h2>
        <ol className="how">
          <li><strong>Prepare an upload</strong> from your Process Maker export.</li>
          <li>Upload that file to OpenFloat yourself.</li>
          <li>
            When it finishes, download OpenFloat's <strong>Transaction Statement</strong> and come
            back to <strong>Check payment results</strong>.
          </li>
        </ol>
        <button type="button" className="button button-block" onClick={() => setRound((n) => n + 1)}>
          Start over with new files
        </button>

        {/* Free text that silently corrupts every phone number if mistyped,
            on a tool only used for Kenyan numbers: out of the way, not beside
            the upload. */}
        <details className="sidebar-settings">
          <summary>Advanced settings</summary>
          <div className="field">
            <label className="field-control">
              <span className="field-label">Country prefix</span>
              <input
                type="text"
                inputMode="numeric"
                value={countryPrefix}
                onChange={(event) => setCountryPrefix(event.target.value)}
                aria-invalid={!prefixValid}
                aria-describedby="prefix-help"
              />
            </label>
            <span className="field-help" id="prefix-help">Country code put in front of phone numbers.</span>
          </div>
          {mode === "transform" && (
            <div className="field">
              <label className="field-control">
                <span className="field-label">Max amount threshold (KES)</span>
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={threshold}
                  onChange={(event) => setThreshold(event.target.value)}
                  aria-invalid={!thresholdValid}
                  aria-describedby="threshold-help"
                />
              </label>
              <span className="field-help" id="threshold-help">Warn when an airtime amount is above this.</span>
            </div>
          )}
        </details>
        {!prefixValid && <Notice tone="error">Country prefix must be 1 to 3 digits, e.g. 254.</Notice>}
        {mode === "transform" && !thresholdValid && (
          <Notice tone="error">The amount threshold must be a whole number, 0 or more.</Notice>
        )}

        <CloseApp onClosed={onClosed} />
        <p className="sidebar-version">Version {defaults.version} · Runs on this computer only</p>
      </aside>

      <main className="main">
        <fieldset className="modes">
          <legend>What do you want to do?</legend>
          {MODES.map((option) => (
            <label key={option.id} className={`mode${mode === option.id ? " mode-selected" : ""}`}>
              <input
                type="radio"
                name="mode"
                value={option.id}
                checked={mode === option.id}
                onChange={() => chooseMode(option.id)}
              />
              <span className="mode-label">{option.label}</span>
              <span className="mode-caption">{option.caption}</span>
            </label>
          ))}
        </fieldset>

        {/* A blank or mistyped prefix would silently rewrite every phone
            number in the batch, so nothing runs until it's a plain code. The
            page stays mounted meanwhile, so the uploaded file isn't lost. */}
        {mode === "transform" ? (
          <TransformPage
            key={round}
            settings={{
              blocked: !prefixValid || !thresholdValid,
              countryPrefix: prefix,
              maxAmountThreshold: thresholdValue,
              defaultAccountNameColumn: defaults.account_name_column,
              defaultProjectCode: defaults.project_code,
            }}
          />
        ) : (
          <StatementPage key={round} settings={{ blocked: !prefixValid, countryPrefix: prefix }} />
        )}
      </main>
    </div>
  );
}

function readMode(): Mode {
  try {
    const saved = localStorage.getItem(MODE_KEY);
    if (saved === "transform" || saved === "statement") return saved;
  } catch {
    // Storage blocked: fall through to the default.
  }
  return "transform";
}

/** Behind a confirmation: one stray click would otherwise lose undownloaded work. */
function CloseApp({ onClosed }: { onClosed: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [error, setError] = useState<unknown>(null);

  async function close() {
    try {
      await shutDown();
      dialog.current?.close();
      onClosed();
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <>
      <button type="button" className="button button-block" onClick={() => dialog.current?.showModal()}>
        Close the app
      </button>
      <dialog ref={dialog} className="dialog" aria-labelledby="close-title">
        <h2 id="close-title">Close the app?</h2>
        <p>
          This stops the OpenFloat Data Formatter and closes its black window. Anything you haven't
          downloaded yet will be lost.
        </p>
        {error !== null && <ErrorNotice message="The app didn't close. Try again." error={error} />}
        <div className="dialog-actions">
          <button type="button" className="button button-primary" onClick={close}>Close the app</button>
          <button type="button" className="button" onClick={() => dialog.current?.close()}>Cancel</button>
        </div>
      </dialog>
    </>
  );
}
