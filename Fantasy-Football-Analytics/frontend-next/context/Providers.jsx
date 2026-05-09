"use client";

import { AuthProvider } from "@/context/AuthContext";
import { PredictionProvider } from "@/context/PredictionContext";

export default function Providers({ children }) {
  return (
    <AuthProvider>
      <PredictionProvider>{children}</PredictionProvider>
    </AuthProvider>
  );
}
