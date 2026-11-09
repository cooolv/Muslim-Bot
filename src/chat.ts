import type { Language, Message } from "./core";

type ChatMessage = Pick<Message, "role" | "content">;

type ChatReply = {
  text: string;
  sources: string[];
};

const apiBaseUrl = import.meta.env.VITE_CHAT_API_URL?.trim();

export const isChatConfigured = Boolean(apiBaseUrl);

export async function askAssistant(
  question: string,
  history: Message[],
  language: Language,
  signal?: AbortSignal,
): Promise<ChatReply> {
  if (!apiBaseUrl) {
    throw new Error(language === "ar"
      ? "خدمة المحادثة غير مُعدّة بعد. يرجى المحاولة لاحقًا."
      : "The chat service is not configured yet. Please try again later.");
  }

  const messages: ChatMessage[] = [
    ...history
      .filter((message) => !message.error)
      .slice(-6)
      .map(({ role, content }) => ({ role, content: content.slice(0, 1000) })),
    { role: "user", content: question },
  ];
  const endpoint = new URL("/api/chat", apiBaseUrl).toString();
  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, language }),
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new Error(language === "ar"
      ? "تعذر الاتصال بالخادم. تحقق من اتصال الإنترنت وحاول مجددًا."
      : "Could not reach the chat server. Check your connection and try again.");
  }

  const result = await response.json().catch(() => null) as
    | (ChatReply & { error?: string })
    | null;
  if (!response.ok) {
    if (response.status === 429) {
      throw new Error(language === "ar"
        ? "وصلت إلى حد الاستخدام المؤقت. انتظر قليلًا ثم حاول مجددًا."
        : "The temporary usage limit was reached. Please wait and try again.");
    }
    if (response.status === 503 || result?.error === "quota_exhausted") {
      throw new Error(language === "ar"
        ? "حصة الخدمة المتاحة انتهت مؤقتًا. حاول لاحقًا."
        : "The available service quota has been exhausted. Please try again later.");
    }
    if (response.status >= 500) {
      throw new Error(language === "ar"
        ? "تعذر على المساعد إكمال الطلب الآن. حاول مجددًا لاحقًا."
        : "The assistant could not complete this request. Please try again later.");
    }
    throw new Error(language === "ar"
      ? "تعذر قبول الطلب. راجع الرسالة وحاول مجددًا."
      : "The request could not be accepted. Check the message and try again.");
  }

  if (!result || typeof result.text !== "string" || !Array.isArray(result.sources)) {
    throw new Error(language === "ar"
      ? "وصل رد غير صالح من الخادم."
      : "The server returned an invalid response.");
  }
  return { text: result.text, sources: result.sources.filter((source): source is string => typeof source === "string") };
}
