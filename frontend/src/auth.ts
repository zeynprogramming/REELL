export type Role = "admin" | "editor" | "viewer";
export type CurrentUser = { id: number; email: string; full_name: string; role: Role; is_active: boolean; created_at: string; last_login_at: string | null };
export type TokenResponse = { access_token: string; token_type: string; expires_in: number; user: CurrentUser };
export const canEdit = (user: CurrentUser) => user.role === "admin" || user.role === "editor";
