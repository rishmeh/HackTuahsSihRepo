import { useState } from "react";
import { toast } from "sonner";
import { trpc } from "@/lib/trpc";

type QuizQuestion = {
  id: number;
  question: string;
  options?: string[];
  answer: string;
  explanation?: string;
  type: string;
};

function QuizCard({ quiz, onDelete }: { quiz: { id: number; topic: string; questions: string; totalQuestions: number; score: number | null; createdAt: Date }; onDelete: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [currentQ, setCurrentQ] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [score, setScore] = useState(0);
  const [done, setDone] = useState(false);

  let questions: QuizQuestion[] = [];
  try { questions = JSON.parse(quiz.questions) as QuizQuestion[]; } catch { /* ignore */ }

  const q = questions[currentQ];
  const totalQ = questions.length;

  const handleAnswer = (ans: string) => {
    if (revealed) return;
    setSelected(ans);
    setRevealed(true);
    const correct = q.answer && (ans.toLowerCase().startsWith(q.answer[0]?.toLowerCase() ?? "") || ans.toLowerCase() === q.answer.toLowerCase());
    if (correct) setScore((s) => s + 1);
  };

  const handleNext = () => {
    if (currentQ < totalQ - 1) {
      setCurrentQ((c) => c + 1);
      setSelected(null);
      setRevealed(false);
    } else {
      setDone(true);
    }
  };

  const resetQuiz = () => { setCurrentQ(0); setSelected(null); setRevealed(false); setScore(0); setDone(false); };

  const scorePercent = quiz.score !== null ? Math.round((quiz.score / (quiz.totalQuestions || 1)) * 100) : null;

  return (
    <div className="rounded-2xl border bg-gradient-to-br from-violet-50 to-purple-50 dark:from-violet-950/30 dark:to-purple-950/30 shadow-sm overflow-hidden">
      <div className="flex items-center justify-between p-4 pb-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl">🧠</span>
            <span className="font-semibold text-sm capitalize">{quiz.topic}</span>
          </div>
          <span className="text-xs text-muted-foreground">
            {quiz.totalQuestions} question{quiz.totalQuestions !== 1 ? "s" : ""}
            {scorePercent !== null ? ` · Last score: ${scorePercent}%` : ""}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => { setExpanded((v) => !v); resetQuiz(); }}
            className="text-xs rounded-lg border px-2 py-1 hover:bg-purple-100 dark:hover:bg-purple-900/50 transition-colors font-medium text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-800"
          >
            {expanded ? "Close" : "Take Quiz"}
          </button>
          <button
            onClick={onDelete}
            className="text-xs rounded-lg border px-2 py-1 hover:bg-red-50 dark:hover:bg-red-900/30 text-red-500 border-red-200 dark:border-red-800 transition-colors"
          >✕</button>
        </div>
      </div>

      {expanded && totalQ > 0 && (
        <div className="px-4 pb-4 border-t border-purple-100 dark:border-purple-900/50 mt-2 pt-3">
          {done ? (
            <div className="text-center py-2">
              <div className="text-3xl mb-2">{score === totalQ ? "🏆" : score >= totalQ / 2 ? "🎉" : "💪"}</div>
              <p className="font-bold text-lg">{score} / {totalQ} correct</p>
              <p className="text-sm text-muted-foreground mb-3">{score === totalQ ? "Perfect!" : "Keep it up!"}</p>
              <button onClick={resetQuiz} style={{ color: "#ffffff" }} className="text-xs rounded-lg bg-purple-600 !text-white px-3 py-1.5 hover:bg-purple-700 transition-colors font-medium">Try Again</button>
            </div>
          ) : (
            <>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs font-medium text-muted-foreground">Question {currentQ + 1} of {totalQ}</span>
                <span className="text-xs text-purple-600 font-medium">{score} correct</span>
              </div>
              <div className="w-full h-1 bg-purple-100 dark:bg-purple-900/50 rounded-full mb-3 overflow-hidden">
                <div className="h-full bg-purple-500 rounded-full transition-all" style={{ width: `${((currentQ) / totalQ) * 100}%` }} />
              </div>
              <p className="font-medium text-sm mb-3 leading-snug">{q.question}</p>
              {q.options && q.options.length > 0 ? (
                <div className="flex flex-col gap-2.5">
                  {q.options.map((opt, i) => {
                    const isSelected = selected === opt;
                    const isCorrect = revealed && (opt.toLowerCase().startsWith(q.answer[0]?.toLowerCase() ?? "") || opt.toLowerCase() === q.answer.toLowerCase());
                    return (
                      <button
                        key={i}
                        onClick={() => handleAnswer(opt)}
                        disabled={revealed}
                        className={`text-left text-xs rounded-xl px-3 py-2.5 border transition-all min-h-[38px] ${
                          isCorrect ? "bg-green-100 border-green-400 dark:bg-green-900/30 dark:border-green-600 font-medium" :
                          isSelected && revealed ? "bg-red-100 border-red-400 dark:bg-red-900/30 dark:border-red-600" :
                          isSelected ? "bg-purple-100 border-purple-400 dark:bg-purple-900/30 dark:border-purple-500" :
                          "bg-white/70 dark:bg-black/20 border-purple-100 dark:border-purple-900 hover:border-purple-300"
                        }`}
                      >
                        {opt}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground italic">
                  {revealed ? <span className="text-green-700 font-medium">Answer: {q.answer}</span> : <button onClick={() => handleAnswer(q.answer)} className="underline text-purple-600">Reveal answer</button>}
                </p>
              )}
              {revealed && (
                <div className="mt-3">
                  {q.explanation && <p className="text-xs text-muted-foreground mt-1 mb-2 italic">{q.explanation}</p>}
                  <button onClick={handleNext} style={{ color: "#ffffff" }} className="text-xs rounded-lg bg-purple-600 !text-white px-3 py-2.5 hover:bg-purple-700 transition-colors w-full mt-1 font-semibold min-h-[38px]">
                    {currentQ < totalQ - 1 ? "Next Question →" : "See Results"}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function QuizzesWidget({ profileId }: { profileId: number }) {
  const { data: quizList, refetch } = trpc.quizzes.listPublic.useQuery({ ownerProfileId: profileId }, { refetchInterval: 3000 });
  const del = trpc.quizzes.delete.useMutation({ onSuccess: () => { refetch(); toast.success("Quiz deleted"); } });

  return (
    <div className="rounded-2xl bg-card border shadow-sm p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-semibold text-base flex items-center gap-2">🧠 My Quizzes</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Say "create a quiz on [topic]" to generate one</p>
        </div>
        <span className="text-xs rounded-full bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 px-2 py-0.5 font-medium">
          {quizList?.length ?? 0}
        </span>
      </div>

      <div className="flex flex-col gap-2 max-h-[600px] overflow-y-auto pr-1">
        {(quizList ?? []).map((quiz) => (
          <QuizCard
            key={quiz.id}
            quiz={{ ...quiz, score: quiz.score ?? null }}
            onDelete={() => del.mutate({ id: quiz.id })}
          />
        ))}
        {!quizList?.length && (
          <div className="text-center py-6">
            <div className="text-3xl mb-2">🧠</div>
            <p className="text-sm text-muted-foreground">No quizzes yet!</p>
            <p className="text-xs text-muted-foreground mt-1">Ask the voice agent to create one</p>
          </div>
        )}
      </div>
    </div>
  );
}
