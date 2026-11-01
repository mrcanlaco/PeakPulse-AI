/**
 * Authentication and Access Security utilities for Đảo Vàng System.
 */

// Keep only a non-sensitive UI marker. The credential is held by the
// server-side HttpOnly session cookie and is never persisted in the browser.
const AUTH_STORAGE_KEY = 'dao_vang_authenticated';

export function getStoredPassword(): string | null {
  try {
    return localStorage.getItem(AUTH_STORAGE_KEY) || null;
  } catch {
    return null;
  }
}

export function setStoredPassword(_password: string): void {
  try {
    localStorage.setItem(AUTH_STORAGE_KEY, '1');
  } catch {
    console.error('Failed to save auth session marker to localStorage');
  }
}

export function clearStoredPassword(): void {
  try {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    document.cookie = 'dao_vang_session=; Path=/; Max-Age=0;';
    document.cookie = 'dao_vang_password=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;';
  } catch {
    console.error('Failed to clear auth session marker from localStorage');
  }
}

export async function verifyPassword(password: string): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch('/api/auth/verify', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ password }),
    });

    const data = await res.json().catch(() => ({}));
    if (res.ok && data?.ok) {
      setStoredPassword(password);
      return { ok: true };
    }
    return {
      ok: false,
      error: data?.error || 'Mật khẩu không chính xác. Vui lòng thử lại.',
    };
  } catch {
    return {
      ok: false,
      error: 'Không thể kết nối đến máy chủ. Vui lòng kiểm tra lại.',
    };
  }
}

export async function checkAuthStatus(): Promise<{ auth_required: boolean; authenticated: boolean }> {
  try {
    const res = await fetch('/api/auth/status', { cache: 'no-store', credentials: 'same-origin' });
    if (!res.ok) {
      return { auth_required: true, authenticated: false };
    }
    return await res.json();
  } catch {
    return { auth_required: true, authenticated: false };
  }
}

export async function logoutAuth(): Promise<void> {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
  } finally {
    clearStoredPassword();
  }
}

let isInterceptorInitialized = false;

/**
 * Adds a consistent API request boundary and catches 401 responses to trigger
 * the lock screen. Authentication is carried by the HttpOnly session cookie.
 */
export function setupFetchAuthInterceptor(): void {
  if (isInterceptorInitialized || typeof window === 'undefined') return;
  isInterceptorInitialized = true;

  const originalFetch = window.fetch;

  window.fetch = async function (input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const isApiRequest = urlStr.includes('/api/');

    const modifiedInit: RequestInit = init ? { ...init } : {};

    if (isApiRequest) {
      const headers = new Headers(
        modifiedInit.headers || (typeof input === 'object' && input && 'headers' in input ? (input as Request).headers : undefined)
      );

      modifiedInit.headers = headers;
      modifiedInit.credentials = modifiedInit.credentials || 'same-origin';
    }

    const response = await originalFetch(input, modifiedInit);

    if (isApiRequest && response.status === 401) {
      if (!urlStr.includes('/api/auth/verify') && !urlStr.includes('/api/auth/status')) {
        const hadAdminSession = Boolean(getStoredPassword());
        clearStoredPassword();
        window.dispatchEvent(
          new CustomEvent('dao_vang_auth_error', {
            detail: { status: 401, url: urlStr, hadAdminSession },
          })
        );
      }
    }

    return response;
  };
}
