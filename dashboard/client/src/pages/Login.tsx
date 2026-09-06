/* Student/parent sign-in: name + short PIN, no email or password. See server/profileAuth.ts. */
import { useState } from "react";
import { GraduationCap, UsersRound } from "lucide-react";
import { trpc } from "@/lib/trpc";

type Role = "student" | "parent";

export default function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [role, setRole] = useState<Role>("student");
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [linkedStudentName, setLinkedStudentName] = useState("");
  const [error, setError] = useState("");

  const login = trpc.profile.login.useMutation({
    onSuccess: () => onLoggedIn(),
    onError: (err) => setError(err.message || "Could not sign in. Please try again."),
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    login.mutate({
      role,
      name,
      pin,
      linkedStudentName: role === "parent" ? linkedStudentName : undefined,
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
            <span className="sun-dot" /> Welcome back
          </div>
          <h1 className="login-title">Sign in to your desk.</h1>

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
            <span>PIN</span>
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

          {role === "parent" && (
            <label className="login-field">
              <span>Your child's name</span>
              <input
                value={linkedStudentName}
                onChange={(event) => setLinkedStudentName(event.target.value)}
                placeholder="Only needed the first time you sign in"
                maxLength={80}
              />
            </label>
          )}

          {error && <div className="upload-status upload-status--error">{error}</div>}

          <button className="modal-primary login-submit" type="submit" disabled={login.isPending}>
            {login.isPending ? "Signing in…" : "Continue"}
          </button>

          <p className="login-hint">
            {role === "student"
              ? "First time here? Just pick a name and a PIN — that becomes your account."
              : "First time here? Enter your child's name once to link your view to theirs."}
          </p>
        </form>
      </div>
    </div>
  );
}
