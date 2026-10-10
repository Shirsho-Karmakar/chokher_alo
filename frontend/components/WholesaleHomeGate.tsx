"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getSession } from "@/lib/api";

export default function WholesaleHomeGate() {
  const router = useRouter();
  useEffect(() => {
    let active = true;
    getSession().then((session) => {
      if (active && session.authenticated && session.wholesale) {
        router.replace("/wholesale/catalogue");
      }
    }).catch(() => {});
    return () => { active = false; };
  }, [router]);
  return null;
}
