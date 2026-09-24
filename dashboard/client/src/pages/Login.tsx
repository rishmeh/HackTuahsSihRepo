/* Student/parent sign-in: name + short PIN, no email or password. See server/profileAuth.ts. */
import { useState } from "react";
import { GraduationCap, UsersRound } from "lucide-react";
import { trpc } from "@/lib/trpc";

type Role = "student" | "parent";
type Mode = "signin" | "signup";

export default function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [role, setRole] = useState<Role>("student");
  const [mode, setMode] = useState<Mode>("signin");
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [linkedStudentName, setLinkedStudentName] = useState("");
  const [linkedStudentPin, setLinkedStudentPin] = useState("");
  const [error, setError] = useState("");

  const login = trpc.profile.login.useMutation({
    onSuccess: () => onLoggedIn(),
    onError: (err) => setError(err.message || "Could not sign in. Please try again."),
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    const linking = role === "parent" && mode === "signup";
    login.mutate({
      mode,
      role,
      name,
      pin,
      linkedStudentName: linking ? linkedStudentName : undefined,
      linkedStudentPin: linking ? linkedStudentPin : undefined,
    });
  };

  return (
    <div className="login-shell">
      <div className="login-brand-panel">
        <div className="brand-lockup" aria-label="TableTot">
          <div className="brand-mark">
            <span className="brand-book" />
            <span className="brand-sun" />
          </div>
          <span className="brand-wordmark">
            table<span>t</span>ot
          </span>
        </div>
        <p className="login-brand-copy">
          One focused block is enough to begin. TableTot keeps a student's study rhythm and gives
          parents a clear, gentle picture of the week &mdash; without hovering.
        </p>
      </div>
      <div className="login-form-panel">
        <form className="login-card" onSubmit={submit}>
          <div className="eyebrow eyebrow--coral">
            <span className="sun-dot" /> {mode === "signin" ? "Welcome back" : "New here"}
          </div>
          <h1 className="login-title">{mode === "signin" ? "Sign in to your desk." : "Create your account."}</h1>

          <div className="role-tabs" role="tablist" aria-label="Choose your role">
            <button
              type="button"
              role="tab"
              aria-selected={role === "student"}
              className={role === "student" ? "role-tab role-tab--active" : "role-tab"}
              onClick={() => setRole("student")}
            >
              <GraduationCap size={15} /> Student
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={role === "parent"}
              className={role === "parent" ? "role-tab role-tab--active" : "role-tab"}
              onClick={() => setRole("parent")}
            >
              <UsersRound size={15} /> Parent
            </button>
          </div>

          <label className="login-field">
            <span>Your name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={role === "student" ? "e.g. Aarav Mehta" : "e.g. Meera Mehta"}
              required
              maxLength={80}
            />
          </label>

          <label className="login-field">
            <span>{mode === "signup" ? "Choose a PIN" : "PIN"}</span>
            <input
              value={pin}
              onChange={(event) => setPin(event.target.value.replace(/[^0-9]/g, ""))}
              placeholder="4 to 8 digits"
              inputMode="numeric"
              type="password"
              required
              minLength={4}
              maxLength={8}
            />
          </label>

          {role === "parent" && mode === "signup" && (
            <>
              <label className="login-field">
                <span>Your child's name</span>
                <input
                  value={linkedStudentName}
                  onChange={(event) => setLinkedStudentName(event.target.value)}
                  placeholder="As they sign in to TableTot"
                  required
                  maxLength={80}
                />
              </label>
              <label className="login-field">
                <span>Your child's PIN</span>
                <input
                  value={linkedStudentPin}
                  onChange={(event) => setLinkedStudentPin(event.target.value.replace(/[^0-9]/g, ""))}
                  placeholder="Ask them to type it in"
                  inputMode="numeric"
                  type="password"
                  required
                  minLength={4}
                  maxLength={8}
                />
              </label>
            </>
          )}

          {error && <div className="upload-status upload-status--error">{error}</div>}

          <button className="modal-primary login-submit" type="submit" disabled={login.isPending}>
            {login.isPending ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
          </button>

          <p className="login-hint">
            {mode === "signin"
              ? "First time here? "
              : "Already have an account? "}
            <button
              type="button"
              className="login-mode-switch"
              onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setError(""); }}
            >
              {mode === "signin" ? "Create an account" : "Sign in instead"}
            </button>
          </p>
          {mode === "signup" && role === "parent" && (
            <p className="login-hint">Your child types their PIN once to link your view to theirs.</p>
          )}
        </form>
      </div>
    </div>
  );
}
