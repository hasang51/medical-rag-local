import { Fragment } from "react";

interface FormattedAnswerProps {
  answer: string;
  citations: string[];
  onCitationClick?: (chunkId: string) => void;
}

const CITATION_TOKEN_REGEX = /(\[[a-z0-9-]+\])/gi;

export function FormattedAnswer({
  answer,
  citations,
  onCitationClick,
}: FormattedAnswerProps) {
  const verifiedSet = new Set(citations);
  const parts = answer.split(CITATION_TOKEN_REGEX);

  return (
    <p className="text-[15px] leading-7 text-slate-800 whitespace-pre-wrap">
      {parts.map((part, idx) => {
        if (part.startsWith("[") && part.endsWith("]")) {
          const chunkId = part.slice(1, -1);
          if (verifiedSet.has(chunkId)) {
            return (
              <button
                key={`${chunkId}-${idx}`}
                type="button"
                onClick={() => onCitationClick?.(chunkId)}
                title={`Doğrulanmış kaynak parça kimliği: ${chunkId}`}
                className="mx-0.5 inline-flex items-center rounded-md border border-teal-200 bg-teal-50 px-1.5 py-0.5 align-baseline font-mono text-xs font-medium text-teal-800 transition-colors hover:border-teal-400 hover:bg-teal-100 cursor-pointer"
              >
                [{chunkId}]
              </button>
            );
          }
        }
        return <Fragment key={idx}>{part}</Fragment>;
      })}
    </p>
  );
}
