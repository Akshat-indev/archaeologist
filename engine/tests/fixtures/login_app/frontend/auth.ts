export async function loginUser() {
  return fetch("/api/login", { method: "POST" });
}
