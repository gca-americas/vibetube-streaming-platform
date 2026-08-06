import os
import sys
import click

from converter import (
    RESOLUTIONS,
    check_ffmpeg,
    transcode_to_mp4,
    transcode_to_hls,
    generate_master_playlist,
    extract_thumbnail
)

@click.command()
@click.argument(
    'input_file',
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True)
)
@click.option(
    '-o', '--output-dir',
    type=click.Path(file_okay=False, dir_okay=True, writable=True),
    help='Directory to store transcoded outputs. Defaults to <input_name>_transcoded/ in the same directory as input.'
)
@click.option(
    '-f', '--format',
    type=click.Choice(['hls', 'mp4', 'all']),
    default='hls',
    help='Output format. hls generates HLS playlists and segments. mp4 generates standard MP4 files. all generates both. Defaults to hls.'
)
@click.option(
    '-r', '--resolution',
    type=click.Choice(['480p', '720p', '1080p', 'all']),
    default='all',
    help='Target resolution. Defaults to all.'
)
def main(input_file, output_dir, format, resolution):
    """
    Vibetube Video Transcoder CLI
    
    Transcodes INPUT_FILE to HLS playlists/segments and/or MP4 format at multiple resolutions (480p, 720p, 1080p).
    """
    # 1. Verify FFmpeg is installed
    if not check_ffmpeg():
        click.secho("Error: 'ffmpeg' command-line tool not found.", fg="red", err=True, bold=True)
        click.echo("Please install FFmpeg and ensure it is in your system PATH.", err=True)
        sys.exit(1)
        
    # 2. Determine and prepare output directory
    input_file_abs = os.path.abspath(input_file)
    if not output_dir:
        input_dir = os.path.dirname(input_file_abs)
        base_name = os.path.splitext(os.path.basename(input_file_abs))[0]
        output_dir = os.path.join(input_dir, f"{base_name}_transcoded")
    else:
        output_dir = os.path.abspath(output_dir)
        
    os.makedirs(output_dir, exist_ok=True)
    
    # 3. Determine resolutions and formats to process
    resolutions_to_process = (
        list(RESOLUTIONS.keys()) if resolution == 'all' else [resolution]
    )
    formats_to_process = (
        ['hls', 'mp4'] if format == 'all' else [format]
    )
    
    # 4. Print transcoding summary
    click.secho("========================================", fg="blue", bold=True)
    click.secho("  Vibetube Video Transcoder Started", fg="blue", bold=True)
    click.secho("========================================", fg="blue", bold=True)
    click.echo(f"Input Video:  {input_file_abs}")
    click.echo(f"Output Dir:   {output_dir}")
    click.echo(f"Resolutions:  {', '.join(resolutions_to_process)}")
    click.echo(f"Formats:      {', '.join(formats_to_process)}")
    click.echo("")
    
    any_failures = False
    
    # 5. Process HLS Format
    if 'hls' in formats_to_process:
        click.secho("-> Generating HLS Playlists & Segments", fg="yellow", bold=True)
        hls_success_resolutions = []
        for res in resolutions_to_process:
            click.echo(f"   [HLS] Processing {res}... ", nl=False)
            try:
                transcode_to_hls(input_file_abs, output_dir, res)
                click.secho("Done", fg="green")
                hls_success_resolutions.append(res)
            except Exception as e:
                click.secho("Failed", fg="red", bold=True)
                click.secho(f"   Error: {e}\n", fg="red", err=True)
                any_failures = True
                
        if hls_success_resolutions:
            try:
                master_playlist = generate_master_playlist(output_dir, hls_success_resolutions)
                click.secho(f"   [HLS] Master playlist created: {master_playlist}", fg="green")
            except Exception as e:
                click.secho("   [HLS] Failed to generate master playlist", fg="red", bold=True)
                click.secho(f"   Error: {e}", fg="red", err=True)
                any_failures = True
        click.echo("")
                
    # 6. Process MP4 Format
    if 'mp4' in formats_to_process:
        click.secho("-> Generating Standalone MP4 Files", fg="yellow", bold=True)
        for res in resolutions_to_process:
            click.echo(f"   [MP4] Processing {res}... ", nl=False)
            try:
                mp4_file = transcode_to_mp4(input_file_abs, output_dir, res)
                click.secho("Done", fg="green")
                click.echo(f"         Saved: {mp4_file}")
            except Exception as e:
                click.secho("Failed", fg="red", bold=True)
                click.secho(f"   Error: {e}\n", fg="red", err=True)
                any_failures = True
        click.echo("")
                
    # 6.5. Extract Thumbnail
    click.secho("-> Extracting Thumbnail Frame", fg="yellow", bold=True)
    try:
        thumbnail_file = extract_thumbnail(input_file_abs, output_dir)
        click.secho("   [Thumbnail] Extraction successful", fg="green")
        click.echo(f"               Saved: {thumbnail_file}")
    except Exception as e:
        click.secho("   [Thumbnail] Extraction failed", fg="red", bold=True)
        click.secho(f"               Error: {e}\n", fg="red", err=True)
        any_failures = True
    click.echo("")

    # 7. Print Completion Status
    click.secho("========================================", fg="blue", bold=True)
    if any_failures:
        click.secho("  Transcoding completed with errors.", fg="yellow", bold=True)
    else:
        click.secho("  Transcoding completed successfully!", fg="green", bold=True)
    click.secho("========================================", fg="blue", bold=True)

if __name__ == '__main__':
    main()
