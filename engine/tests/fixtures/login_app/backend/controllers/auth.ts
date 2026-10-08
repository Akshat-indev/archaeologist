import { authService } from "../services/auth";

export async function loginController() {
  return authService.login();
}
