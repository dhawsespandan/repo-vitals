/** Shared API types. Mirrors the backend serializers; grows each phase. */

export interface User {
  id: string;
  username: string;
  name: string;
  email: string;
  avatarUrl: string;
}

export interface SessionResponse {
  authenticated: boolean;
  user: User | null;
}

/**
 * Every backend failure arrives in this shape (`apps/common/errors.py`).
 * From Phase 2 the pre-scan validation outcomes are identified by `code`
 * alone, so the frontend branches on the code and never on the message text.
 */
export interface ApiErrorBody {
  code: string;
  message: string;
  [key: string]: unknown;
}
