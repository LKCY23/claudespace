ObjC.import('AppKit');

function artwork(original) {
    const pixels = $.NSBitmapImageRep.imageRepWithData(original.TIFFRepresentation);
    const width = pixels.pixelsWide;
    const height = pixels.pixelsHigh;
    const midX = Math.floor(width / 2);
    const midY = Math.floor(height / 2);
    let left = 0, right = width - 1, top = 0, bottom = height - 1;
    while (left < midX && pixels.colorAtXY(left, midY).alphaComponent < 0.95) left++;
    while (right > midX && pixels.colorAtXY(right, midY).alphaComponent < 0.95) right--;
    while (top < midY && pixels.colorAtXY(midX, top).alphaComponent < 0.95) top++;
    while (bottom > midY && pixels.colorAtXY(midX, bottom).alphaComponent < 0.95) bottom--;

    return {
        rect: $.NSMakeRect(
            left * original.size.width / width,
            (height - bottom - 1) * original.size.height / height,
            (right - left + 1) * original.size.width / width,
            (bottom - top + 1) * original.size.height / height
        ),
        background: pixels.colorAtXY(Math.round(left + (right - left) * 0.04), midY)
            .colorUsingColorSpace($.NSColorSpace.sRGBColorSpace).colorWithAlphaComponent(1)
    };
}

function run(arguments) {
    if (arguments.length !== 2) {
        throw new Error('Expected the source app and output PNG paths.');
    }

    const original = $.NSWorkspace.sharedWorkspace.iconForFile($(arguments[0]));
    const source = artwork(original);
    const image = $.NSImage.alloc.initWithSize($.NSMakeSize(1024, 1024));
    image.lockFocus;

    // macOS supplies the enclosure; transparent padding would add a second plate.
    source.background.setFill;
    $.NSBezierPath.bezierPathWithRect($.NSMakeRect(0, 0, 1024, 1024)).fill;
    original.drawInRectFromRectOperationFraction(
        $.NSMakeRect(0, 0, 1024, 1024), source.rect, $.NSCompositingOperationSourceOver, 1
    );

    $.NSColor.colorWithSRGBRedGreenBlueAlpha(1, 0.98, 0.94, 1).setFill;
    $.NSBezierPath.bezierPathWithOvalInRect($.NSMakeRect(650, 50, 310, 310)).fill;
    $.NSColor.colorWithSRGBRedGreenBlueAlpha(0.13, 0.30, 0.29, 1).setFill;
    $.NSBezierPath.bezierPathWithOvalInRect($.NSMakeRect(666, 66, 278, 278)).fill;

    $.NSColor.colorWithSRGBRedGreenBlueAlpha(1, 0.98, 0.94, 1).setFill;
    const play = $.NSBezierPath.bezierPath;
    play.moveToPoint($.NSMakePoint(770, 125));
    play.lineToPoint($.NSMakePoint(770, 285));
    play.lineToPoint($.NSMakePoint(885, 205));
    play.closePath;
    play.fill;

    image.unlockFocus;
    const representation = $.NSBitmapImageRep.imageRepWithData(image.TIFFRepresentation);
    const png = representation.representationUsingTypeProperties($.NSPNGFileType, $.NSDictionary.alloc.init);
    if (!png.writeToFileAtomically($(arguments[1]), true)) {
        throw new Error('Could not write the icon PNG.');
    }
}
