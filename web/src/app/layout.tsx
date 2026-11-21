import type { Metadata } from "next";
import "./globals.css";

import { Nav } from "@/components/nav";

export const metadata: Metadata = {
  title: "StockScanner",
  description: "Scan, browse and analyze stocks worldwide",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <Nav />
        {children}
      </body>
    </html>
  );
}
