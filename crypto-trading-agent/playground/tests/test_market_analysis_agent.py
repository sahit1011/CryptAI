    timeframes = args.timeframes.split(',')
    
    tester = MarketAnalysisAgentTester()
    
    try:
        await tester.setup()
        
        results = await tester.test_live_analysis(
            symbol=args.symbol,
            timeframes=timeframes
        )
        
        console.print("\n[bold green]✅ Test Complete![/bold green]")
        
    except Exception as e:
        console.print(f"\n[bold red]❌ Test Failed: {e}[/bold red]")
        raise
    
    finally:
        await tester.teardown()


if __name__ == "__main__":
    asyncio.run(main())
