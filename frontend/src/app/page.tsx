import { HeroSection } from "@/components/landing/HeroSection";

import { ArchitectureSection } from "@/components/landing/ArchitectureSection";

import { CTASection } from "@/components/landing/CTASection";
import { Footer } from "@/components/landing/Footer";
import { Navbar } from "@/components/landing/Navbar";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0A0A0A] text-foreground overflow-x-hidden font-sans selection:bg-indigo-500/30">

      {/* Enhanced Navbar */}
      <Navbar />

      <main>
        <HeroSection />

        <ArchitectureSection />
        <CTASection />
      </main>

      <Footer />
    </div>
  );
}
