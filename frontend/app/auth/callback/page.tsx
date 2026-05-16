"use client";
import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function AuthCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    // If Google/Supabase returned an error (e.g. user cancelled), go back to login
    const error = searchParams.get("error") ?? window.location.hash.match(/error=([^&]+)/)?.[1];
    if (error) {
      router.replace("/login");
      return;
    }

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_IN" && session) {
        subscription.unsubscribe();
        router.replace("/");
      } else if (event === "SIGNED_OUT" || (event !== "INITIAL_SESSION" && !session)) {
        subscription.unsubscribe();
        router.replace("/login");
      }
    });

    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        subscription.unsubscribe();
        router.replace("/");
      }
    });

    // Fallback: if nothing resolves in 5s, send to login
    const timeout = setTimeout(() => {
      subscription.unsubscribe();
      router.replace("/login");
    }, 5000);

    return () => {
      subscription.unsubscribe();
      clearTimeout(timeout);
    };
  }, [router, searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-5 h-5 border-2 border-gray-300 border-t-purple-500 rounded-full animate-spin" />
    </div>
  );
}
