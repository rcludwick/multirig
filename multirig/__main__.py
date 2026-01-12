"""
Main entry point for MultiRig application.

Can be run as:
- python -m multirig (starts the web server)
- python -m multirig --help (shows help)
"""
import argparse
import logging
import sys


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MultiRig - Control and sync multiple ham radio rigs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m multirig                    Start with default profile
  python -m multirig --profile contest  Start with contest profile
  python -m multirig --host 0.0.0.0     Bind to all interfaces
  python -m multirig --port 8080        Use custom port
  
Environment Variables:
  MULTIRIG_PROFILE    Configuration profile to use (default: default)
  MULTIRIG_CONFIG_DIR Configuration directory (default: ~/.multirig)
        """
    )
    
    parser.add_argument(
        "--profile",
        "-p",
        default="default",
        help="Configuration profile to use (default: default)"
    )
    
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)"
    )
    
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development mode)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Logging level (default: info)"
    )
    
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version="MultiRig 0.2.0 (Zenoh Edition)"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Set profile environment variable for application
    import os
    os.environ["MULTIRIG_PROFILE"] = args.profile
    
    # Start the server
    try:
        import uvicorn
        uvicorn.run(
            "multirig.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level
        )
    except KeyboardInterrupt:
        print("\nShutting down MultiRig...")
        sys.exit(0)
    except Exception as e:
        print(f"Error starting MultiRig: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
