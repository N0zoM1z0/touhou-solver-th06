#include <algorithm>
#include <cmath>
#include <cstdint>

#ifdef _WIN32
#define TH06_EXPORT extern "C" __declspec(dllexport)
#else
#define TH06_EXPORT extern "C"
#endif

namespace {

struct Aabb {
    float left;
    float top;
    float right;
    float bottom;
};

struct LaserHazard {
    float originX;
    float originY;
    float angle;
    float centerOffset;
    float sizeX;
    float sizeY;
};

struct SafeResult {
    std::int32_t safe;
    float clearance;
    float finalX;
    float finalY;
};

struct Direction {
    std::int32_t dx;
    std::int32_t dy;
};

constexpr Direction kActions[9] = {
    {0, 0}, {0, -1}, {0, 1}, {-1, 0}, {1, 0},
    {-1, -1}, {1, -1}, {-1, 1}, {1, 1},
};
constexpr std::int32_t kDelays[4] = {0, 1, 2, 3};

Direction actionFromInput(std::uint16_t mask) {
    Direction result{0, 0};
    if ((mask & 0x10U) != 0U) {
        result.dy = -1;
        if ((mask & 0x40U) != 0U) result.dx = -1;
        if ((mask & 0x80U) != 0U) result.dx = 1;
    } else if ((mask & 0x20U) != 0U) {
        result.dy = 1;
        if ((mask & 0x40U) != 0U) result.dx = -1;
        if ((mask & 0x80U) != 0U) result.dx = 1;
    } else {
        if ((mask & 0x40U) != 0U) result.dx = -1;
        if ((mask & 0x80U) != 0U) result.dx = 1;
    }
    return result;
}

void stepPlayer(float& x, float& y, Direction action, float cardinal, float diagonal) {
    const float speed = action.dx != 0 && action.dy != 0 ? diagonal : cardinal;
    x = std::clamp(x + static_cast<float>(action.dx) * speed, 8.0F, 376.0F);
    y = std::clamp(y + static_cast<float>(action.dy) * speed, 16.0F, 432.0F);
}

float signedClearance(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    const Aabb& hazard
) {
    const float gapX = std::max(
        hazard.left - (playerX + playerHalfWidth),
        (playerX - playerHalfWidth) - hazard.right
    );
    const float gapY = std::max(
        hazard.top - (playerY + playerHalfHeight),
        (playerY - playerHalfHeight) - hazard.bottom
    );
    if (gapX <= 0.0F && gapY <= 0.0F) return std::max(gapX, gapY);
    return std::hypot(std::max(0.0F, gapX), std::max(0.0F, gapY));
}

float signedLaserClearance(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    const LaserHazard& laser
) {
    const float dx = playerX - laser.originX;
    const float dy = playerY - laser.originY;
    const float sine = std::sin(laser.angle);
    const float cosine = std::cos(laser.angle);
    const float localX = cosine * dx + sine * dy;
    const float localY = cosine * dy - sine * dx;
    const Aabb box{
        laser.centerOffset - laser.sizeX / 2.0F,
        -laser.sizeY / 2.0F,
        laser.centerOffset + laser.sizeX / 2.0F,
        laser.sizeY / 2.0F,
    };
    return signedClearance(localX, localY, playerHalfWidth, playerHalfHeight, box);
}

}  // namespace

TH06_EXPORT std::int32_t th06_certify_actions(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t horizon,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    SafeResult* output
) {
    if (horizon <= 0 || horizon > 64 || bulletOffsets == nullptr || laserOffsets == nullptr || output == nullptr) {
        return -1;
    }
    const Direction current = actionFromInput(inputMask);
    const bool currentFocus = (inputMask & 0x04U) != 0U;
    const float currentCardinal = currentFocus ? focusSpeed : normalSpeed;
    const float currentDiagonal = currentFocus ? focusDiagonalSpeed : normalDiagonalSpeed;

    for (std::int32_t actionIndex = 0; actionIndex < 9; ++actionIndex) {
        SafeResult result{1, 999.0F, playerX, playerY};
        for (const std::int32_t delay : kDelays) {
            float x = playerX;
            float y = playerY;
            for (std::int32_t frame = 1; frame <= horizon; ++frame) {
                const bool oldInput = frame <= delay;
                stepPlayer(
                    x,
                    y,
                    oldInput ? current : kActions[actionIndex],
                    oldInput ? currentCardinal : focusSpeed,
                    oldInput ? currentDiagonal : focusDiagonalSpeed
                );
                const std::uint32_t bulletStart = bulletOffsets[frame - 1];
                const std::uint32_t bulletEnd = bulletOffsets[frame];
                for (std::uint32_t index = bulletStart; index < bulletEnd; ++index) {
                    const float clearance = signedClearance(
                        x, y, playerHalfWidth, playerHalfHeight, bullets[index]
                    );
                    result.clearance = std::min(result.clearance, clearance);
                    if (clearance <= collisionMargin) {
                        result.safe = 0;
                        break;
                    }
                }
                if (result.safe == 0) break;
                const std::uint32_t laserStart = laserOffsets[frame - 1];
                const std::uint32_t laserEnd = laserOffsets[frame];
                for (std::uint32_t index = laserStart; index < laserEnd; ++index) {
                    const float clearance = signedLaserClearance(
                        x, y, playerHalfWidth, playerHalfHeight, lasers[index]
                    );
                    result.clearance = std::min(result.clearance, clearance);
                    if (clearance <= collisionMargin) {
                        result.safe = 0;
                        break;
                    }
                }
                if (result.safe == 0) break;
            }
            if (result.safe == 0) break;
            if (delay == kDelays[3]) {
                result.finalX = x;
                result.finalY = y;
            }
        }
        output[actionIndex] = result;
    }
    return 0;
}

// This is a proposal score only. candidateMask must already come from the
// hard authority; the result can rank those candidates but cannot add one.
TH06_EXPORT std::int32_t th06_replanning_scores(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t split,
    std::int32_t horizon,
    std::uint16_t candidateMask,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    std::int32_t* output
) {
    if (
        split <= 0 || horizon <= split || horizon > 64 ||
        bulletOffsets == nullptr || laserOffsets == nullptr || output == nullptr
    ) {
        return -1;
    }
    const Direction current = actionFromInput(inputMask);
    const bool currentFocus = (inputMask & 0x04U) != 0U;
    const float currentCardinal = currentFocus ? focusSpeed : normalSpeed;
    const float currentDiagonal = currentFocus ? focusDiagonalSpeed : normalDiagonalSpeed;
    for (std::int32_t firstIndex = 0; firstIndex < 9; ++firstIndex) {
        output[firstIndex] = 0;
        if ((candidateMask & (1U << firstIndex)) == 0U) continue;
        std::int32_t worstDelayCount = 9;
        for (const std::int32_t firstDelay : kDelays) {
            float splitX = playerX;
            float splitY = playerY;
            for (std::int32_t frame = 1; frame <= split; ++frame) {
                const bool oldInput = frame <= firstDelay;
                stepPlayer(
                    splitX,
                    splitY,
                    oldInput ? current : kActions[firstIndex],
                    oldInput ? currentCardinal : focusSpeed,
                    oldInput ? currentDiagonal : focusDiagonalSpeed
                );
            }
            std::int32_t continuationCount = 0;
            for (std::int32_t secondIndex = 0; secondIndex < 9; ++secondIndex) {
                bool survived = true;
                for (const std::int32_t secondDelay : kDelays) {
                    float x = splitX;
                    float y = splitY;
                    for (std::int32_t frame = split + 1; frame <= horizon; ++frame) {
                        const bool oldInput = frame - split <= secondDelay;
                        stepPlayer(
                            x,
                            y,
                            oldInput ? kActions[firstIndex] : kActions[secondIndex],
                            focusSpeed,
                            focusDiagonalSpeed
                        );
                        const std::uint32_t bulletStart = bulletOffsets[frame - 1];
                        const std::uint32_t bulletEnd = bulletOffsets[frame];
                        for (std::uint32_t index = bulletStart; index < bulletEnd; ++index) {
                            if (
                                signedClearance(
                                    x, y, playerHalfWidth, playerHalfHeight, bullets[index]
                                ) <= collisionMargin
                            ) {
                                survived = false;
                                break;
                            }
                        }
                        if (!survived) break;
                        const std::uint32_t laserStart = laserOffsets[frame - 1];
                        const std::uint32_t laserEnd = laserOffsets[frame];
                        for (std::uint32_t index = laserStart; index < laserEnd; ++index) {
                            if (
                                signedLaserClearance(
                                    x, y, playerHalfWidth, playerHalfHeight, lasers[index]
                                ) <= collisionMargin
                            ) {
                                survived = false;
                                break;
                            }
                        }
                        if (!survived) break;
                    }
                    if (!survived) break;
                }
                continuationCount += static_cast<std::int32_t>(survived);
            }
            worstDelayCount = std::min(worstDelayCount, continuationCount);
        }
        output[firstIndex] = worstDelayCount;
    }
    return 0;
}
