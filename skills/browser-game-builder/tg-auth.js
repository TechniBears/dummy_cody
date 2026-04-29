/**
 * Telegram Mini App auth guard.
 * Checks the user is:
 *   1. Opening from inside Telegram (WebApp context)
 *   2. On the allowed user list (numeric Telegram IDs)
 *
 * To add a tester: add their numeric Telegram ID to ALLOWED_IDS.
 * They can get their ID by messaging @userinfobot in Telegram.
 */
const TG_AUTH = (function () {

  // --- ALLOWLIST ---
  // Add numeric Telegram user IDs here.
  const ALLOWED_IDS = [
    000000000,   // principal (configure your Telegram ID)
    // additional tester — pending proper tenant isolation
  ];

  const DEV_MODE = false; // set true only for local testing without Telegram

  function init() {
    if (DEV_MODE) {
      window.TG_USER = null;
      window.TG_THEME = { bg: '#0d0d0d', text: '#00ff88' };
      return true;
    }

    if (!window.Telegram || !window.Telegram.WebApp) {
      _block('This game is only available inside Telegram.\nOpen it from @YOUR_BOT_NAME.');
      return false;
    }

    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand();

    const user = tg.initDataUnsafe?.user;
    const userId = user?.id;

    if (!userId) {
      _block('Could not identify your Telegram account.\nTry reopening from @YOUR_BOT_NAME.');
      return false;
    }

    if (!ALLOWED_IDS.includes(userId)) {
      _block(`Access restricted.\nYour ID (${userId}) is not on the tester list.\nAsk @YOUR_HANDLE to add you.`);
      return false;
    }

    window.TG_USER = user;
    window.TG_THEME = {
      bg: tg.backgroundColor || '#0d0d0d',
      text: tg.themeParams?.text_color || '#00ff88',
    };

    return true;
  }

  function _block(msg) {
    document.body.innerHTML = `
      <div style="
        min-height:100vh;display:flex;flex-direction:column;
        align-items:center;justify-content:center;
        background:#0d0d0d;color:#ff4466;
        font-family:'Courier New',monospace;text-align:center;padding:32px;
        line-height:1.6;
      ">
        <div style="font-size:2.5rem;margin-bottom:20px;">🔒</div>
        <div style="font-size:0.95rem;max-width:300px;">${msg.replace(/\n/g,'<br>')}</div>
      </div>`;
  }

  return { init };
})();
