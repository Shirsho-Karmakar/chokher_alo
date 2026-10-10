import PhoneLogin from "@/components/PhoneLogin";

export const metadata = { title: "Sign in" };
export default function LoginPage() {
  return <div className="auth-wrap"><div className="auth-art"><div><div className="eyebrow" style={{color: "#8fc6d5"}}>Retail account</div><h1>One number. Your orders, prescriptions and bag.</h1></div><p>Sign in with your mobile number to keep your bag, prescriptions and orders together in one secure account.</p></div><div className="auth-panel"><div className="auth-card"><h2>Sign in or create account</h2><p>We’ll send a one-time code to your Indian mobile number.</p><PhoneLogin/><div className="auth-note">By continuing, you agree to receive a one-time authentication code on your mobile number.</div></div></div></div>;
}
