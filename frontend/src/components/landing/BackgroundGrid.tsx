"use client";

import { cn } from "@/lib/utils";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";

export const BackgroundGrid = () => {
    const [stars, setStars] = useState<Array<{
        x: string;
        y: string;
        opacity: number;
        destinationY: string;
        duration: number;
    }>>([]);

    useEffect(() => {
        const generatedStars = [...Array(20)].map(() => ({
            x: Math.random() * 100 + "%",
            y: Math.random() * 100 + "%",
            opacity: Math.random(),
            destinationY: Math.random() * -100 + "%",
            duration: Math.random() * 10 + 10,
        }));
        setStars(generatedStars);
    }, []);

    return (
        <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
            {/* Radial Gradient for Spotlight effect */}
            <div className="absolute top-[-20%] left-1/2 -translate-x-1/2 w-[1000px] h-[500px] bg-indigo-500/20 blur-[120px] rounded-full opacity-50" />

            {/* Grid Perspective */}
            <div
                className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]"
                style={{
                    maskImage: "linear-gradient(to bottom, transparent, black 10%, black 90%, transparent)"
                }}
            />

            {/* Moving Stars / Particles */}
            <div className="absolute inset-0">
                {stars.map((star, i) => (
                    <motion.div
                        key={i}
                        className="absolute w-1 h-1 bg-white rounded-full"
                        initial={{
                            x: star.x,
                            y: star.y,
                            opacity: star.opacity
                        }}
                        animate={{
                            y: [null, star.destinationY],
                            opacity: [0, 1, 0]
                        }}
                        transition={{
                            duration: star.duration,
                            repeat: Infinity,
                            ease: "linear"
                        }}
                    />
                ))}
            </div>
        </div>
    );
};
