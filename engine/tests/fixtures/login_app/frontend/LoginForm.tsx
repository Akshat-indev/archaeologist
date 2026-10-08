import { loginUser } from "./auth";

export function LoginForm() {
  async function handleSubmit() {
    validateForm();
    await loginUser();
    unresolvedCall();
  }

  function validateForm() {
    return true;
  }

  return <form onSubmit={handleSubmit} />;
}
