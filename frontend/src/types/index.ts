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

/** A registered repository (`apps/repositories/serializers.py`). */
export interface Repository {
  id: string;
  owner: string;
  name: string;
  fullName: string;
  htmlUrl: string;
  defaultBranch: string;
  visibility: "public" | "private";
  accessLevel: "owner" | "write" | "collaborator";
  registeredAt: string;
}

/**
 * Registration has two *successful* shapes, which is why it is not just
 * `Repository`. §5.6 answers a duplicate with 200 and the existing row rather
 * than an error: the user asked for something they already have, and the
 * useful answer is where to find it.
 */
export type RegisterResult =
  | { outcome: "created"; repository: Repository }
  | { outcome: "duplicate"; repository: Repository; message: string };
