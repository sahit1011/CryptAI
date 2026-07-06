import { Navbar } from "@/components/landing/Navbar";
import { HeroSection } from "@/components/landing/HeroSection";
import { FeaturesSection } from "@/components/landing/FeaturesSection";
import { StatsSection } from "@/components/landing/StatsSection";
import { ArchitectureSection } from "@/components/landing/ArchitectureSection";
import { CTASection } from "@/components/landing/CTASection";
import { Footer } from "@/components/landing/Footer";

/*
 * Landing composition — one continuous crimson atmosphere on bg-background.
 * Order: Hero (with its own aurora) → Features → Stats → Architecture → CTA.
 * Selection is crimson to match the brand. No hardcoded canvas hex.
 */
export default function LandingPage() {
    return (
        <div className="min-h-screen bg-background text-foreground overflow-x-hidden font-sans selection:bg-accent/30 selection:text-foreground">
            <Navbar />

            <main>
                <HeroSection />
                <FeaturesSection />
                <StatsSection />
                <ArchitectureSection />
                <CTASection />
            </main>

            <Footer />
        </div>
    );
}
