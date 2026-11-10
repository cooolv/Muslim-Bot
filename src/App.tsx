import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  ArrowLeft,
  Bell,
  BellOff,
  BookOpen,
  CircleHelp,
  Clock3,
  Copy,
  ExternalLink,
  Globe2,
  Heart,
  History,
  LoaderCircle,
  LocateFixed,
  MapPin,
  Menu,
  MessageCircle,
  Moon,
  Plus,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Sun,
  Trash2,
  X,
} from "lucide-react";
import {
  countries,
  clearLocalData,
  DEFAULT_SETTINGS,
  getActiveConversationId,
  loadConversations,
  loadSettings,
  newId,
  nextPrayer,
  persistConversations,
  prayerNames,
  saveSettings,
  setActiveConversationId,
} from "./core";
import type { Conversation, KnowledgeDocument, Message, Page, PrayerName, Settings } from "./core";
import { askAssistant, isChatConfigured } from "./chat";

const suggestions = [
  { ar: "رشح لي تطبيقًا إسلاميًا مفيدًا", en: "Recommend a helpful Islamic app", icon: "✦" },
  { ar: "ما أفضل تطبيق لحفظ القرآن؟", en: "What's a good app for memorizing Quran?", icon: "۞" },
  { ar: "كيف أحافظ على أذكار الصباح والمساء؟", en: "How can I keep up with daily adhkar?", icon: "☼" },
  { ar: "أرني مواقيت الصلاة في مدينتي", en: "Show prayer times for my city", icon: "◷" },
];

type PrayerData = {
  timings: Partial<Record<PrayerName, string>>;
  hijri: string;
  timezone: string;
};

type SavedCity = { name: string; country: string; lat: number; lon: number; method: number };

function makeConversation(title: string): Conversation {
  return {
    id: newId(),
    title,
    updatedAt: Date.now(),
    messages: [],
  };
}

function App() {
  const [settings, setSettings] = useState<Settings>(() => loadSettings());
  const [conversations, setConversations] = useState<Conversation[]>(() => {
    const saved = loadConversations();
    return saved.length ? saved : [makeConversation("محادثة جديدة")];
  });
  const [page, setPage] = useState<Page>("chat");
  const [menuOpen, setMenuOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [knowledge, setKnowledge] = useState<KnowledgeDocument[]>([]);
  const [knowledgeError, setKnowledgeError] = useState("");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [userName, setUserName] = useState("");
  const [activeId, setActiveId] = useState(() => {
    const savedId = getActiveConversationId();
    return savedId && conversations.some((conversation) => conversation.id === savedId)
      ? savedId
      : conversations[0]?.id ?? "";
  });
  const controllerRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  const active = conversations.find((conversation) => conversation.id === activeId) ?? conversations[0];
  const messages = active?.messages ?? [];
  const isEnglish = settings.language === "en";

  const text = useCallback((ar: string, en: string) => (isEnglish ? en : ar), [isEnglish]);

  const pageTitle = useMemo(() => {
    switch (page) {
      case "chat": return text("المساعد", "Assistant");
      case "prayer": return text("مواقيت الصلاة", "Prayer times");
      case "settings": return text("الإعدادات", "Settings");
      case "about": return text("حول المساعد", "About");
      case "privacy": return text("الخصوصية", "Privacy");
      default: return text("المساعد", "Assistant");
    }
  }, [page, text]);

  useEffect(() => {
    document.documentElement.lang = settings.language;
    document.documentElement.dir = isEnglish ? "ltr" : "rtl";
    document.documentElement.dataset.theme = settings.theme;
    document.documentElement.dataset.accent = settings.accentColor;
  }, [settings.language, settings.theme, settings.accentColor, isEnglish]);

  useEffect(() => {
    saveSettings(settings);
  }, [settings]);

  useEffect(() => {
    persistConversations(conversations);
  }, [conversations]);

  useEffect(() => {
    if (activeId) setActiveConversationId(activeId);
  }, [activeId]);

  useEffect(() => {
    const knowledgeUrl = new URL("./knowledge.json", window.location.href).toString();
    fetch(knowledgeUrl)
      .then((response) => {
        if (!response.ok) throw new Error("Knowledge file is not available.");
        return response.json() as Promise<KnowledgeDocument[]>;
      })
      .then((records) => {
        if (!Array.isArray(records)) throw new Error("Knowledge file is invalid.");
        setKnowledge(records.filter((record) => record && typeof record.title === "string" && typeof record.body === "string"));
      })
      .catch(() => setKnowledgeError(text("تعذر تحميل ملف المعرفة المحلي.", "Could not load the local knowledge file.")));
  }, [text]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 2500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const updateSettings = useCallback((patch: Partial<Settings>) => {
    setSettings((current) => ({ ...current, ...patch }));
  }, []);

  const selectPage = useCallback((nextPage: Page) => {
    setPage(nextPage);
    setMenuOpen(false);
  }, []);

  const updateActive = useCallback((updater: (conversation: Conversation) => Conversation) => {
    setConversations((items) => items.map((conversation) => conversation.id === activeId ? updater(conversation) : conversation));
  }, [activeId]);

  const newConversation = useCallback(() => {
    const next = makeConversation(text("محادثة جديدة", "New conversation"));
    setConversations((items) => [...items, next]);
    setActiveId(next.id);
    setPage("chat");
    setInput("");
    setMenuOpen(false);
  }, [text]);

  const deleteConversation = useCallback((id: string) => {
    const remaining = conversations.filter((conversation) => conversation.id !== id);
    if (!remaining.length) {
      const next = makeConversation(text("محادثة جديدة", "New conversation"));
      setConversations([next]);
      setActiveId(next.id);
    } else {
      setConversations(remaining);
      if (activeId === id) setActiveId(remaining[0].id);
    }
    setToast(text("تم حذف المحادثة", "Conversation deleted"));
  }, [activeId, conversations, text]);

  const copyMessage = useCallback(async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setToast(text("تم نسخ النص", "Copied"));
    } catch {
      setToast(text("تعذر النسخ", "Copy failed"));
    }
  }, [text]);

  const answerQuestion = useCallback(async (question: string, priorMessages = messages) => {
    if (!activeId || busy) return;
    const userMessage: Message = { id: newId(), role: "user", content: question, createdAt: Date.now() };
    const nextTitle = active?.title && active.title !== "محادثة جديدة" ? active.title : question.trim().slice(0, 40);
    updateActive((conversation) => ({
      ...conversation,
      title: nextTitle || text("محادثة جديدة", "New conversation"),
      updatedAt: Date.now(),
      messages: [...conversation.messages, userMessage],
    }));
    setInput("");
    setBusy(true);
    const abortController = new AbortController();
    controllerRef.current = abortController;
    try {
      const result = await askAssistant(question, priorMessages, settings.language, abortController.signal);
      const assistantMessage: Message = {
        id: newId(),
        role: "assistant",
        content: result.text,
        createdAt: Date.now(),
        sources: result.sources,
      };
      setConversations((items) => items.map((conversation) => conversation.id === activeId
        ? { ...conversation, updatedAt: Date.now(), messages: [...conversation.messages, assistantMessage] }
        : conversation));
    } catch (error) {
      if (!abortController.signal.aborted) {
        const detail = error instanceof Error ? error.message : text("حدث خطأ غير متوقع.", "An unexpected error occurred.");
        const failure: Message = {
          id: newId(),
          role: "assistant",
          content: `${text("تعذر إكمال الطلب:", "Request failed:")} ${detail}`,
          createdAt: Date.now(),
          error: true,
        };
        setConversations((items) => items.map((conversation) => conversation.id === activeId
          ? { ...conversation, updatedAt: Date.now(), messages: [...conversation.messages, failure] }
          : conversation));
      }
    } finally {
      if (controllerRef.current === abortController) controllerRef.current = null;
      setBusy(false);
    }
  }, [active, activeId, busy, messages, settings.language, text, updateActive]);

  const submit = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || busy) return;
    void answerQuestion(trimmed, messages);
  }, [answerQuestion, busy, input, messages]);

  const regenerate = useCallback(() => {
    if (busy) return;
    let lastUserIndex = -1;
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index].role === "user") {
        lastUserIndex = index;
        break;
      }
    }
    if (lastUserIndex < 0) return;
    const question = messages[lastUserIndex].content;
    const history = messages.slice(0, lastUserIndex);
    updateActive((conversation) => ({
      ...conversation,
      messages: conversation.messages.slice(0, lastUserIndex + 1),
    }));
    void answerQuestion(question, history);
  }, [answerQuestion, busy, messages, updateActive]);

  const settingsPage = (
    <div className="content-page settings-page">
      <div className="page-intro">
        <div className="page-icon"><Settings2 size={20} /></div>
        <div>
          <h1>{text("الإعدادات", "Settings")}</h1>
          <p>{text("خصص لغة الواجهة والمظهر. لا تحتاج إلى مفتاح API.", "Choose your language and theme. No API key is needed.")}</p>
        </div>
      </div>
      <div className="settings-grid">
        <div className="settings-card">
          <h3>{text("تفضيلات العرض", "Display preferences")}</h3>
          <label className="field-group">{text("لغة الواجهة", "Interface language")}
            <select value={settings.language} onChange={(event) => updateSettings({ language: event.target.value as Settings["language"] })}>
              <option value="ar">العربية</option>
              <option value="en">English</option>
            </select>
          </label>
          <label className="field-group">{text("المظهر", "Theme")}
            <select value={settings.theme} onChange={(event) => updateSettings({ theme: event.target.value as Settings["theme"] })}>
              <option value="dark">{text("داكن", "Dark")}</option>
              <option value="light">{text("فاتح", "Light")}</option>
            </select>
          </label>
          <label className="field-group">{text("حجم نص الرسائل", "Message text size")}
            <select value={settings.messageSize} onChange={(event) => updateSettings({ messageSize: event.target.value as Settings["messageSize"] })}>
              <option value="small">{text("صغير", "Small")}</option>
              <option value="medium">{text("متوسط (افتراضي)", "Medium (default)")}</option>
              <option value="large">{text("كبير", "Large")}</option>
              <option value="extra-large">{text("كبير جدًا", "Extra large")}</option>
            </select>
          </label>
          <fieldset className="accent-picker">
            <legend>{text("لون التمييز", "Accent color")}</legend>
            <div className="accent-options">
              {([
                ["green", "أخضر", "Green"],
                ["blue", "أزرق", "Blue"],
                ["violet", "بنفسجي", "Violet"],
                ["amber", "كهرماني", "Amber"],
              ] as const).map(([color, arName, enName]) => (
                <button
                  key={color}
                  type="button"
                  className={`accent-option ${settings.accentColor === color ? "selected" : ""}`}
                  aria-pressed={settings.accentColor === color}
                  onClick={() => updateSettings({ accentColor: color })}
                >
                  <span className={`accent-swatch accent-${color}`} />
                  {text(arName, enName)}
                </button>
              ))}
            </div>
          </fieldset>
          <label className="settings-toggle">
            <span>
              <strong>{text("تمييز رد المساعد بلون مختلف", "Use a different color for assistant replies")}</strong>
              <small>{text("يساعد على التفريق بين ردود المساعد ورسائلك.", "Makes assistant replies easier to distinguish from your messages.")}</small>
            </span>
            <input
              type="checkbox"
              checked={settings.distinguishMessages}
              onChange={(event) => updateSettings({ distinguishMessages: event.target.checked })}
            />
          </label>
        </div>
      </div>
      <div className="settings-actions">
        <button className="secondary-button" type="button" onClick={() => {
          setSettings(DEFAULT_SETTINGS);
          setToast(text("تمت استعادة تفضيلات العرض الافتراضية", "Default display preferences restored"));
        }}>
          {text("استعادة الإعدادات الافتراضية", "Restore default preferences")}
        </button>
        <button className="secondary-button" type="button" onClick={() => {
          clearLocalData();
          const next = makeConversation("محادثة جديدة");
          setConversations([next]);
          setActiveId(next.id);
          setSettings(DEFAULT_SETTINGS);
          setUserName("");
          setToast(text("تم حذف البيانات المحلية", "Local data cleared"));
        }}>
          {text("حذف كل البيانات المحلية", "Delete all local data")}
        </button>
      </div>
    </div>
  );

  return (
    <div className={`app-shell ${menuOpen ? "menu-open" : ""}`} data-language={settings.language} data-message-size={settings.messageSize} data-distinguish-messages={settings.distinguishMessages}>
      {menuOpen && <button aria-label={text("إغلاق القائمة", "Close menu")} className="mobile-backdrop" onClick={() => setMenuOpen(false)} />}
      <aside className="sidebar">
        <div className="brand-row">
          <div className="brand-mark"><span>م</span></div>
          <div className="brand-copy"><strong>{text("مساعد المسلم", "Muslim Assistant")}</strong><span>Muslim Assistant</span></div>
          <button className="icon-button mobile-close" aria-label={text("إغلاق", "Close")} onClick={() => setMenuOpen(false)}><X size={18} /></button>
        </div>
        <button className="new-chat-button" onClick={newConversation}><Plus size={18} />{text("محادثة جديدة", "New chat")}</button>
        <nav className="side-nav">
          <button className={page === "chat" ? "nav-item active" : "nav-item"} onClick={() => selectPage("chat")}><MessageCircle size={18} />{text("المساعد", "Assistant")}</button>
          <button className={page === "prayer" ? "nav-item active" : "nav-item"} onClick={() => selectPage("prayer")}><Clock3 size={18} />{text("مواقيت الصلاة", "Prayer times")}</button>
          <button className={page === "settings" ? "nav-item active" : "nav-item"} onClick={() => selectPage("settings")}><Settings2 size={18} />{text("الإعدادات", "Settings")}</button>
        </nav>
        <div className="sidebar-section-heading">
          <span>{text("محادثاتك", "Your chats")}</span>
          <button className="tiny-button" aria-label={text("إظهار السجل", "Show history")} onClick={() => setHistoryOpen((open) => !open)}><History size={15} /></button>
        </div>
        <div className="conversation-list">
          {(historyOpen ? [...conversations].sort((a, b) => b.updatedAt - a.updatedAt) : [...conversations].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, 7)).map((conversation) => (
            <div className={`conversation-row ${conversation.id === activeId ? "selected" : ""}`} key={conversation.id}>
              <button onClick={() => { setActiveId(conversation.id); setPage("chat"); }} title={conversation.title}>
                <span>{conversation.title || text("محادثة جديدة", "New conversation")}</span>
              </button>
              <button className="delete-chat" aria-label={text("حذف المحادثة", "Delete conversation")} onClick={() => deleteConversation(conversation.id)}><Trash2 size={15} /></button>
            </div>
          ))}
        </div>
        <div className="sidebar-bottom">
          <div className="privacy-chip"><ShieldCheck size={16} /><span>{text("محادثاتك تبقى على جهازك", "Your chats stay on your device")}</span></div>
          <button className="nav-item" onClick={() => selectPage("about")}><CircleHelp size={18} />{text("حول المساعد", "About")}</button>
          <button className="nav-item" onClick={() => selectPage("privacy")}><ShieldCheck size={18} />{text("الخصوصية", "Privacy")}</button>
          <div className="sidebar-user">
            <div className="user-avatar">م</div>
            <input value={userName} onChange={(event) => setUserName(event.target.value)} placeholder={text("اسم اختياري", "Optional name")} maxLength={24} />
            <button className="theme-toggle" aria-label={text("تبديل المظهر", "Toggle theme")} onClick={() => updateSettings({ theme: settings.theme === "dark" ? "light" : "dark" })}>
              {settings.theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <button className="icon-button menu-trigger" aria-label={text("فتح القائمة", "Open menu")} onClick={() => setMenuOpen(true)}><Menu size={20} /></button>
          <div className="mobile-brand"><div className="mini-mark">م</div><span>{text("مساعد المسلم", "Muslim Assistant")}</span></div>
          <div className="topbar-title">{pageTitle}</div>
          <div className="topbar-actions">
            <div className={`connection-pill ${isChatConfigured ? "configured" : ""}`}><span className="status-dot" />{isChatConfigured ? text("المساعد متاح", "Assistant available") : text("الخادم غير مُعدّ", "Server not configured")}</div>
            <button className="icon-button" aria-label={text("الإعدادات", "Settings")} onClick={() => selectPage("settings")}><Settings2 size={18} /></button>
          </div>
        </header>

        {page === "chat" && (
          <section className={`chat-page ${messages.length ? "has-messages" : ""}`}>
            <div className="chat-scroll-area">
              {messages.length === 0 ? (
                <div className="welcome-panel">
                  <div className="welcome-emblem"><Sparkles size={24} /></div>
                  <div className="eyebrow">{text("رفيقك في التطبيقات النافعة", "Your companion for beneficial apps")}</div>
                  <h1>{text("السلام عليكم", "Assalamu alaikum")}{userName ? `، ${userName}` : ""}<br /><span>{text("كيف أساعدك اليوم؟", "How can I help today?")}</span></h1>
                  <p>{text("اسأل عن التطبيقات الإسلامية، أو ابدأ بسؤال يشغلك.", "Ask about Islamic apps, prayer times, or general guidance.")}</p>
                  <div className="suggestion-grid">
                    {suggestions.map((item) => (
                      <button key={item.en} onClick={() => void answerQuestion(text(item.ar, item.en), messages)}>
                        <span className="suggestion-icon">{item.icon}</span>
                        <span>{text(item.ar, item.en)}</span>
                        <ArrowLeft size={16} className="suggestion-arrow" />
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="message-list">
                  {messages.map((message, index) => (
                    <MessageBubble
                      key={message.id}
                      message={message}
                      isEnglish={isEnglish}
                      onCopy={() => void copyMessage(message.content)}
                      onRegenerate={regenerate}
                      showRegenerate={message.role === "assistant" && index === messages.length - 1}
                      text={text}
                    />
                  ))}
                  {busy && (
                    <div className="thinking-row">
                      <div className="assistant-avatar">م</div>
                      <div className="thinking-bubble">
                        <span className="thinking-dots"><i /><i /><i /></span>
                        <span>{text("يفكر في إجابة مناسبة", "Thinking through your request")}</span>
                      </div>
                    </div>
                  )}
                  <div ref={endRef} />
                </div>
              )}
            </div>
            <div className="composer-wrap">
              {knowledge.length === 0 && !knowledgeError && (
                <div className="corpus-note"><BookOpen size={14} />{text("قاعدة التطبيقات المحلية فارغة — يمكن للمساعد الإجابة عن الأسئلة العامة، لكنه لن ينسب معلومات تطبيقات إلى مصادر غير موجودة.", "The local app knowledge base is empty — general answers are available, but app details will not be attributed to missing sources.")}</div>
              )}
              {knowledgeError && <div className="inline-warning">{knowledgeError}</div>}
              <form className="composer" onSubmit={(event) => { event.preventDefault(); submit(); }}>
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      submit();
                    }
                  }}
                  placeholder={text("اسأل مساعد تطبيقات المسلم...", "Message Muslim Assistant...")}
                  rows={1}
                />
                {busy ? (
                  <button className="stop-button" type="button" onClick={() => controllerRef.current?.abort()}>{text("إيقاف", "Stop")}</button>
                ) : (
                  <button className="send-button" type="submit"><Send size={18} /></button>
                )}
              </form>
            </div>
          </section>
        )}

        {page === "prayer" && <PrayerPage isEnglish={isEnglish} text={text} />}
        {page === "settings" && settingsPage}
        {page === "about" && <InfoPage kind="about" isEnglish={isEnglish} text={text} />}
        {page === "privacy" && <InfoPage kind="privacy" isEnglish={isEnglish} text={text} />}
      </main>

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}

function PrayerPage({ isEnglish, text }: { isEnglish: boolean; text: (ar: string, en: string) => string }) {
  const [country, setCountry] = useState<string>(countries[0][0]);
  const [city, setCity] = useState("");
  const [method, setMethod] = useState(3);
  const [savedCity, setSavedCity] = useState<SavedCity | null>(null);
  const [prayers, setPrayers] = useState<PrayerData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notify, setNotify] = useState(false);

  const selectedCountry = useMemo(() => countries.find((item) => item[0] === country) ?? countries[0], [country]);
  const nowSince = useMemo(() => new Date(), []);

  const loadPrayerTimes = useCallback(async (place: SavedCity) => {
    setLoading(true);
    setError("");
    setSavedCity(place);
    localStorage.setItem("muslim-assistant-city", JSON.stringify(place));
    try {
      const url = new URL("https://api.aladhan.com/v1/timings/" + Math.floor(Date.now() / 1000));
      url.searchParams.set("latitude", String(place.lat));
      url.searchParams.set("longitude", String(place.lon));
      url.searchParams.set("method", String(place.method));
      const response = await fetch(url);
      if (!response.ok) throw new Error(text("تعذر جلب مواقيت الصلاة.", "Could not load prayer times."));
      const payload = await response.json() as {
        code?: number;
        data?: {
          timings?: Record<string, string>;
          date?: { hijri?: { day?: string; month?: { ar?: string; en?: string }; year?: string } };
          meta?: { timezone?: string };
        };
      };
      if (payload.code !== 200 || !payload.data?.timings) throw new Error(text("استجابة غير صالحة من خدمة المواقيت.", "Invalid response from the prayer service."));
      const hijri = payload.data.date?.hijri;
      setPrayers({
        timings: Object.fromEntries((Object.keys(prayerNames) as PrayerName[]).map((key) => [key, payload.data?.timings?.[key] ? payload.data.timings[key].split(" ")[0] : "--:--"])) as PrayerData["timings"],
        hijri: hijri ? `${hijri.day ?? ""} ${isEnglish ? hijri.month?.en ?? "" : hijri.month?.ar ?? ""} ${hijri.year ?? ""}` : "",
        timezone: payload.data.meta?.timezone ?? "UTC",
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : text("تعذر تحميل مواقيت الصلاة.", "Unable to load prayer times."));
    } finally {
      setLoading(false);
    }
  }, [isEnglish, text]);

  useEffect(() => {
    const saved = localStorage.getItem("muslim-assistant-city");
    if (!saved) return;
    try {
      const parsed = JSON.parse(saved) as SavedCity;
      setSavedCity(parsed);
      void loadPrayerTimes(parsed);
    } catch {
      localStorage.removeItem("muslim-assistant-city");
    }
  }, [loadPrayerTimes]);

  useEffect(() => {
    const saved = localStorage.getItem("muslim-assistant-reminders");
    setNotify(saved === "on");
  }, []);

  const findCity = useCallback(async () => {
    if (!city.trim()) {
      setError(text("اكتب اسم المدينة أولًا.", "Enter a city first."));
      return;
    }
    setLoading(true);
    setError("");
    try {
      const url = new URL("https://nominatim.openstreetmap.org/search");
      url.searchParams.set("q", `${city.trim()}, ${selectedCountry[2]}`);
      url.searchParams.set("format", "jsonv2");
      url.searchParams.set("limit", "1");
      url.searchParams.set("accept-language", isEnglish ? "en" : "ar");
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(text("تعذر البحث عن المدينة.", "Could not search for that city."));
      const results = await response.json() as Array<{ lat: string; lon: string; name?: string }>;
      if (!results.length) throw new Error(text("لم نعثر على المدينة. جرّب اسمًا آخر.", "City not found. Try another name."));
      const place: SavedCity = {
        name: results[0].name || city.trim(),
        country: isEnglish ? selectedCountry[2] : selectedCountry[1],
        lat: Number(results[0].lat),
        lon: Number(results[0].lon),
        method,
      };
      await loadPrayerTimes(place);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : text("تعذر البحث عن المدينة.", "City lookup failed."));
    } finally {
      setLoading(false);
    }
  }, [city, isEnglish, loadPrayerTimes, method, selectedCountry, text]);

  const locateMe = useCallback(() => {
    if (!navigator.geolocation) {
      setError(text("تحديد الموقع غير متاح في هذا المتصفح.", "Geolocation is not available in this browser."));
      return;
    }
    setLoading(true);
    setError("");
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        const place: SavedCity = {
          name: text("موقعي الحالي", "My location"),
          country: isEnglish ? selectedCountry[2] : selectedCountry[1],
          lat: coords.latitude,
          lon: coords.longitude,
          method,
        };
        await loadPrayerTimes(place);
      },
      () => {
        setLoading(false);
        setError(text("لم يتم السماح بتحديد الموقع. يمكنك إدخال مدينتك يدويًا.", "Location permission was denied. You can enter your city instead."));
      },
      { timeout: 10000 },
    );
  }, [isEnglish, loadPrayerTimes, method, selectedCountry, text]);

  const toggleNotifications = useCallback(async () => {
    if (!("Notification" in window)) {
      setError(text("الإشعارات غير مدعومة في هذا المتصفح.", "Notifications are not supported in this browser."));
      return;
    }
    const permission = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
    if (permission !== "granted") {
      setError(text("لم يتم السماح بالإشعارات.", "Notification permission was not granted."));
      return;
    }
    const nextState = !notify;
    localStorage.setItem("muslim-assistant-reminders", nextState ? "on" : "off");
    setNotify(nextState);
  }, [notify, text]);

  const upcoming = prayers ? nextPrayer(prayers.timings, new Date(), prayers.timezone) : null;

  return (
    <div className="content-page prayer-page">
      <div className="page-intro">
        <div className="page-icon"><Clock3 size={20} /></div>
        <div>
          <h1>{text("مواقيت الصلاة", "Prayer times")}</h1>
          <p>{text("حدد مدينتك أو استخدم موقعك للحصول على أوقات الصلوات الخمس.", "Choose your city or use your location to see the five daily prayer times.")}</p>
        </div>
      </div>

      {prayers && savedCity ? (
        <div className="prayer-layout">
          <section className="prayer-main-card">
            <div className="prayer-location">
              <div className="location-symbol"><MapPin size={18} /></div>
              <div>
                <strong>{savedCity.name}{savedCity.country ? `، ${savedCity.country}` : ""}</strong>
                <span>{prayers.timezone}</span>
              </div>
              <button className="text-button" onClick={() => setPrayers(null)}>{text("تغيير", "Change")}</button>
            </div>
            <div className="prayer-date">
              <span>{new Intl.DateTimeFormat(isEnglish ? "en" : "ar", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: prayers.timezone }).format(nowSince)}</span>
              <span className="hijri-date">{prayers.hijri} {text("هـ", "AH")}</span>
            </div>
            <div className="next-prayer-card">
              <div className="next-prayer-pattern">۞</div>
              <div><span>{text("الصلاة القادمة", "Next prayer")}</span><strong>{upcoming ? prayerNames[upcoming.name][isEnglish ? "en" : "ar"] : "—"}</strong></div>
              <div className="countdown-block"><span>{text("متبقي", "Time left")}</span><strong dir="ltr">{upcoming ? `${Math.floor((upcoming.time.getTime() - Date.now()) / 1000 / 60)}:${String(Math.floor(((upcoming.time.getTime() - Date.now()) / 1000) % 60)).padStart(2, "0")}` : "--:--"}</strong></div>
            </div>
            <div className="prayer-list">
              {(Object.keys(prayerNames) as PrayerName[]).map((name) => {
                const time = prayers.timings[name] ?? "--:--";
                const isNext = upcoming?.name === name;
                return (
                  <div className={`prayer-time-row ${isNext ? "upcoming" : ""}`} key={name}>
                    <span className="prayer-time-icon">{name === "Fajr" ? "☼" : name === "Dhuhr" ? "◉" : name === "Asr" ? "◌" : name === "Maghrib" ? "☼" : "☾"}</span>
                    <span className="prayer-name">{prayerNames[name][isEnglish ? "en" : "ar"]}{isNext && <small>{text("القادمة", "Next")}</small>}</span>
                    <strong dir="ltr">{time}</strong>
                  </div>
                );
              })}
            </div>
            <div className="prayer-result-actions">
              <button className={`secondary-button ${notify ? "reminders-enabled" : ""}`} onClick={() => void toggleNotifications()}>
                {notify ? <Bell size={16} /> : <BellOff size={16} />}
                {notify ? text("التذكير مفعّل أثناء فتح الموقع", "Reminders on while the site is open") : text("تفعيل تذكيرات المتصفح", "Enable browser reminders")}
              </button>
            </div>
          </section>
          <aside className="prayer-aside">
            <div className="prayer-tip-card"><div className="tip-icon"><Heart size={18} /></div><h3>{text("معلومة مهمة", "Important note")}</h3><p>{text("المواقيت تقديرية وقد تختلف عن التقويم المحلي. تأكد من المذاهب والتقويم المعتمد في مدينتك.", "Prayer times are estimates and may differ from your local calendar. Verify with your local mosque or trusted authority.")}</p><a href="https://aladhan.com/calculation-methods" target="_blank" rel="noreferrer">{text("عن طرق الحساب", "About calculation methods")}<ExternalLink size={13} /></a></div>
          </aside>
        </div>
      ) : (
        <div className="prayer-empty">
          <div className="prayer-illustration">☾</div>
          <h2>{text("اكتشف مواقيت الصلاة", "Find your prayer times")}</h2>
          <p>{text("اختر مدينتك يدويًا أو استخدم الموقع الجغرافي عند الموافقة.", "Enter your city or share your location with consent.")}</p>
          <div className="city-form">
            <div className="form-grid">
              <div className="field-group">
                <label htmlFor="country-select">{text("الدولة", "Country")}</label>
                <select id="country-select" value={country} onChange={(event) => { setCountry(event.target.value); const next = countries.find((item) => item[0] === event.target.value); if (next) setMethod(next[3]); }}>
                  {countries.map((item) => <option key={item[0]} value={item[0]}>{isEnglish ? item[2] : item[1]}</option>)}
                </select>
              </div>
              <div className="field-group">
                <label htmlFor="city-name">{text("المدينة", "City")}</label>
                <input id="city-name" value={city} onChange={(event) => setCity(event.target.value)} placeholder={text("مثال: القاهرة", "e.g. Cairo")} />
              </div>
            </div>
            <div className="field-group">
              <label htmlFor="calculation-method">{text("طريقة الحساب", "Calculation method")}</label>
              <select id="calculation-method" value={method} onChange={(event) => setMethod(Number(event.target.value))}>
                <option value={3}>{text("رابطة العالم الإسلامي", "Muslim World League")}</option>
                <option value={1}>{text("جامعة العلوم الإسلامية، كراتشي", "University of Islamic Sciences, Karachi")}</option>
                <option value={2}>{text("الجمعية الإسلامية لأمريكا الشمالية", "ISNA")}</option>
                <option value={4}>{text("أم القرى، مكة", "Umm Al-Qura, Makkah")}</option>
                <option value={5}>{text("الهيئة المصرية العامة للمساحة", "Egyptian General Authority")}</option>
                <option value={12}>{text("اتحاد المنظمات الإسلامية في فرنسا", "Union of Islamic Organisations of France")}</option>
                <option value={13}>{text("رئاسة الشؤون الدينية التركية", "Diyanet")}</option>
              </select>
            </div>
            {error && <div className="inline-warning">{error}</div>}
            <div className="city-actions">
              <button className="primary-button" onClick={() => void findCity()} disabled={loading}>{loading ? <LoaderCircle className="spin" size={16} /> : <MapPin size={16} />}{text("عرض المواقيت", "Show prayer times")}</button>
              <button className="secondary-button" onClick={locateMe} disabled={loading}><LocateFixed size={16} />{text("استخدم موقعي", "Use my location")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function InfoPage({ text, kind }: { isEnglish: boolean; text: (ar: string, en: string) => string; kind: "about" | "privacy" }) {
  const about = kind === "about";
  return (
    <div className="content-page info-page">
      <div className="page-intro">
        <div className="page-icon">{about ? <Sparkles size={20} /> : <ShieldCheck size={20} />}</div>
        <div>
          <h1>{about ? text("حول مساعد المسلم", "About Muslim Assistant") : text("الخصوصية", "Privacy")}</h1>
          <p>{about ? text("مساعد إسلامي بسيط، خاص، ومفتوح المصدر.", "A thoughtful, private, open-source Islamic assistant.") : text("ما الذي يحدث لبياناتك عند استخدام الموقع.", "How your information is handled by this site.")}</p>
        </div>
      </div>
      {about ? (
        <div className="info-card about-card">
          <div className="about-logo">م</div>
          <h2>{text("مساعد تطبيقات المسلم", "Muslim Assistant")}</h2>
          <p>{text("واجهة ويب تساعد المستخدمين على اكتشاف التطبيقات الإسلامية النافعة ومراجعة مواقيت الصلاة وطرح الأسئلة عبر مساعد مدعوم بـ Gemini.", "A web app for discovering beneficial Islamic apps, checking prayer times, and asking questions with a Gemini-powered assistant.")}</p>
          <div className="about-values">
            <div><ShieldCheck size={18} /><strong>{text("خصوصية محلية", "Local privacy")}</strong><span>{text("لا حسابات أو خادم رئيسي", "No accounts or central server")}</span></div>
            <div><Globe2 size={18} /><strong>{text("مفتوح للجميع", "Open access")}</strong><span>{text("يعمل على GitHub Pages", "Runs on GitHub Pages")}</span></div>
          </div>
          <div className="disclaimer-card">
            <strong>{text("تنبيه شرعي", "Religious disclaimer")}</strong>
            <p>{text("المساعد ليس مفتيًا. قد يخطئ الذكاء الاصطناعي، ولا تُعتمد إجاباته كفتوى. للمسائل الشرعية المعقدة أو الشخصية، راجع أهل العلم الثقات.", "This assistant is not a mufti. AI can be wrong, and its answers are not fatwas. For personal or complex religious questions, consult trusted scholars.")}</p>
          </div>
        </div>
      ) : (
        <div className="info-card privacy-content">
          <h2>{text("البيانات التي تبقى على جهازك", "Data that stays on your device")}</h2>
          <p>{text("تُحفظ المحادثات وتفضيلات العرض على جهازك. يمر نص السؤال وسياق المحادثة المحدود عبر خادم المساعد إلى Google Gemini؛ لا يُرسل مفتاح API إلى المتصفح.", "Chats and display preferences stay on your device. Your question and limited conversation context are sent through the assistant server to Google Gemini; the API key is never sent to your browser.")}</p>
          <h2>{text("البيانات التي تغادر جهازك", "Data sent to other services")}</h2>
          <ul>
            <li>{text("يُرسل نص المحادثة إلى Google Gemini لمعالجة الرد. لا تسأل عن معلومات شخصية أو مالية حساسة.", "Conversation text is sent to Google Gemini to generate a response. Do not share sensitive personal or financial information.")}</li>
            <li>{text("طلب مواقيت الصلاة أو البحث عن المدن يرسل البيانات إلى Aladhan وOpenStreetMap عند استخدام تلك الخصائص.", "Prayer-time and city-lookup requests go to Aladhan and OpenStreetMap when you use those features.")}</li>
          </ul>
          <div className="disclaimer-card">
            <strong>{text("حذف بياناتك", "Delete your data")}</strong>
            <p>{text("استخدم «حذف كل البيانات المحلية» في الإعدادات لإزالة المحادثات والإعدادات المحفوظة من هذا المتصفح.", "Use “Delete all local data” in Settings to remove saved chats and preferences from this browser.")}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function MessageBubble({
  message,
  isEnglish,
  text,
  onCopy,
  onRegenerate,
  showRegenerate,
}: {
  message: Message;
  isEnglish: boolean;
  text: (ar: string, en: string) => string;
  onCopy: () => void;
  onRegenerate: () => void;
  showRegenerate: boolean;
}) {
  const isUser = message.role === "user";
  const sources = (message.sources ?? []).filter((source) => {
    try {
      return new URL(source).protocol === "https:";
    } catch {
      return false;
    }
  });
  return (
    <div className={`message-row ${isUser ? "user-row" : "assistant-row"}`}>
      {!isUser && <div className="assistant-avatar">م</div>}
      <div className={`message-bubble ${isUser ? "user-bubble" : "assistant-bubble"}`}>
        {message.error ? <div className="error-box">{message.content}</div> : <ReactMarkdown>{message.content}</ReactMarkdown>}
        {!isUser && !message.error && sources.length > 0 && (
          <div className="source-list" aria-label={text("مصادر الإجابة", "Answer sources")}>
            <span>{text("المصادر", "Sources")}</span>
            {sources.map((source, index) => (
              <a key={`${source}-${index}`} href={source} target="_blank" rel="noreferrer">
                {text(`المصدر ${index + 1}`, `Source ${index + 1}`)}
                <ExternalLink size={12} />
              </a>
            ))}
          </div>
        )}
        {!isUser && (
          <div className="message-actions">
            <button onClick={onCopy} aria-label={text("نسخ", "Copy")}><Copy size={14} /></button>
            {showRegenerate && <button onClick={onRegenerate} aria-label={text("إعادة توليد", "Regenerate")}>
              <ArrowLeft size={14} />
            </button>}
          </div>
        )}
      </div>
      {isUser && <div className="user-avatar">{isEnglish ? "U" : "م"}</div>}
    </div>
  );
}

export default App;
