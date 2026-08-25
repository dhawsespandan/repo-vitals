import { ConfirmDialog } from "../components/ConfirmDialog";

interface LogoutConfirmProps {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/**
 * The one dialog Phase 1 ships. It is reached two ways — the "Sign out" button
 * and the back-navigation guard — and the copy explains the second case,
 * because a dialog that appears after a back gesture is otherwise baffling.
 */
export function LogoutConfirm({ open, onCancel, onConfirm }: LogoutConfirmProps) {
  return (
    <ConfirmDialog
      open={open}
      title="Sign out?"
      body="You'll be returned to the login screen. Back-navigation while signed in shows this confirmation rather than silently exposing the login page."
      cancelLabel="Stay signed in"
      confirmLabel="Sign out"
      onCancel={onCancel}
      onConfirm={onConfirm}
    />
  );
}
