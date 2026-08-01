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
constexpr std::uint16_t kActionMasks[9] = {
    0x00U, 0x10U, 0x20U, 0x40U, 0x80U,
    0x50U, 0x90U, 0x60U, 0xA0U,
};
constexpr std::uint16_t kDirectionBits[4] = {0x20U, 0x40U, 0x80U, 0x10U};
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

bool sameDirection(Direction left, Direction right) {
    return left.dx == right.dx && left.dy == right.dy;
}

std::int32_t transitionDirections(
    std::uint16_t currentMask,
    std::uint16_t targetMask,
    Direction output[4]
) {
    currentMask &= 0xF0U;
    targetMask &= 0xF0U;
    std::uint16_t prefixMask = currentMask;
    const Direction current = actionFromInput(currentMask);
    const Direction target = actionFromInput(targetMask);
    std::int32_t count = 0;
    const auto append = [&](Direction prefix) {
        if (sameDirection(prefix, current) || sameDirection(prefix, target)) return;
        for (std::int32_t index = 0; index < count; ++index) {
            if (sameDirection(prefix, output[index])) return;
        }
        output[count++] = prefix;
    };
    // Keyboard::_sync sorts movement key names as down, left, right, up,
    // publishing every release before every press in one SendInput batch.
    for (const std::uint16_t bit : kDirectionBits) {
        if ((currentMask & bit) != 0U && (targetMask & bit) == 0U) {
            prefixMask &= ~bit;
            append(actionFromInput(prefixMask));
        }
    }
    for (const std::uint16_t bit : kDirectionBits) {
        if ((targetMask & bit) != 0U && (currentMask & bit) == 0U) {
            prefixMask |= bit;
            append(actionFromInput(prefixMask));
        }
    }
    return count;
}

Direction scheduledDirection(
    std::int32_t frame,
    std::int32_t delay,
    Direction current,
    Direction target,
    const Direction* transition
) {
    if (transition != nullptr) {
        if (frame < delay) return current;
        if (frame == delay) return *transition;
        return target;
    }
    return frame <= delay ? current : target;
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

bool safeAtFrame(
    float x,
    float y,
    float playerHalfWidth,
    float playerHalfHeight,
    std::int32_t frameIndex,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    float* clearance
) {
    const std::uint32_t bulletStart = bulletOffsets[frameIndex];
    const std::uint32_t bulletEnd = bulletOffsets[frameIndex + 1];
    for (std::uint32_t index = bulletStart; index < bulletEnd; ++index) {
        const float value = signedClearance(
            x, y, playerHalfWidth, playerHalfHeight, bullets[index]
        );
        if (clearance != nullptr) *clearance = std::min(*clearance, value);
        if (value <= collisionMargin) return false;
    }
    const std::uint32_t laserStart = laserOffsets[frameIndex];
    const std::uint32_t laserEnd = laserOffsets[frameIndex + 1];
    for (std::uint32_t index = laserStart; index < laserEnd; ++index) {
        const float value = signedLaserClearance(
            x, y, playerHalfWidth, playerHalfHeight, lasers[index]
        );
        if (clearance != nullptr) *clearance = std::min(*clearance, value);
        if (value <= collisionMargin) return false;
    }
    return true;
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
        Direction transitions[4];
        const std::int32_t transitionCount = transitionDirections(
            inputMask, kActionMasks[actionIndex], transitions
        );
        for (const std::int32_t delay : kDelays) {
            const std::int32_t branchCount = 1 + (delay > 0 ? transitionCount : 0);
            for (std::int32_t branch = 0; branch < branchCount; ++branch) {
                const Direction* transition = branch == 0 ? nullptr : &transitions[branch - 1];
                float x = playerX;
                float y = playerY;
                for (std::int32_t frame = 1; frame <= horizon; ++frame) {
                    const bool currentSpeed = transition == nullptr
                        ? frame <= delay
                        : frame < delay;
                    stepPlayer(
                        x,
                        y,
                        scheduledDirection(
                            frame, delay, current, kActions[actionIndex], transition
                        ),
                        currentSpeed ? currentCardinal : focusSpeed,
                        currentSpeed ? currentDiagonal : focusDiagonalSpeed
                    );
                    if (!safeAtFrame(
                        x,
                        y,
                        playerHalfWidth,
                        playerHalfHeight,
                        frame - 1,
                        bulletOffsets,
                        bullets,
                        laserOffsets,
                        lasers,
                        collisionMargin,
                        &result.clearance
                    )) {
                        result.safe = 0;
                        break;
                    }
                }
                if (result.safe == 0) break;
                if (delay == kDelays[3] && branch == 0) {
                    result.finalX = x;
                    result.finalY = y;
                }
            }
            if (result.safe == 0) break;
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
        Direction firstTransitions[4];
        const std::int32_t firstTransitionCount = transitionDirections(
            inputMask, kActionMasks[firstIndex], firstTransitions
        );
        std::int32_t worstBranchCount = 9;
        for (const std::int32_t firstDelay : kDelays) {
            const std::int32_t firstBranchCount = 1 + (
                firstDelay > 0 ? firstTransitionCount : 0
            );
            for (std::int32_t firstBranch = 0; firstBranch < firstBranchCount; ++firstBranch) {
                const Direction* firstTransition = firstBranch == 0
                    ? nullptr
                    : &firstTransitions[firstBranch - 1];
                float splitX = playerX;
                float splitY = playerY;
                for (std::int32_t frame = 1; frame <= split; ++frame) {
                    const bool currentSpeed = firstTransition == nullptr
                        ? frame <= firstDelay
                        : frame < firstDelay;
                    stepPlayer(
                        splitX,
                        splitY,
                        scheduledDirection(
                            frame,
                            firstDelay,
                            current,
                            kActions[firstIndex],
                            firstTransition
                        ),
                        currentSpeed ? currentCardinal : focusSpeed,
                        currentSpeed ? currentDiagonal : focusDiagonalSpeed
                    );
                }
                std::int32_t continuationCount = 0;
                for (std::int32_t secondIndex = 0; secondIndex < 9; ++secondIndex) {
                    Direction secondTransitions[4];
                    const std::int32_t secondTransitionCount = transitionDirections(
                        kActionMasks[firstIndex],
                        kActionMasks[secondIndex],
                        secondTransitions
                    );
                    bool survived = true;
                    for (const std::int32_t secondDelay : kDelays) {
                        const std::int32_t secondBranchCount = 1 + (
                            secondDelay > 0 ? secondTransitionCount : 0
                        );
                        for (
                            std::int32_t secondBranch = 0;
                            secondBranch < secondBranchCount;
                            ++secondBranch
                        ) {
                            const Direction* secondTransition = secondBranch == 0
                                ? nullptr
                                : &secondTransitions[secondBranch - 1];
                            float x = splitX;
                            float y = splitY;
                            for (std::int32_t frame = split + 1; frame <= horizon; ++frame) {
                                const std::int32_t elapsed = frame - split;
                                stepPlayer(
                                    x,
                                    y,
                                    scheduledDirection(
                                        elapsed,
                                        secondDelay,
                                        kActions[firstIndex],
                                        kActions[secondIndex],
                                        secondTransition
                                    ),
                                    focusSpeed,
                                    focusDiagonalSpeed
                                );
                                if (!safeAtFrame(
                                    x,
                                    y,
                                    playerHalfWidth,
                                    playerHalfHeight,
                                    frame - 1,
                                    bulletOffsets,
                                    bullets,
                                    laserOffsets,
                                    lasers,
                                    collisionMargin,
                                    nullptr
                                )) {
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
                worstBranchCount = std::min(worstBranchCount, continuationCount);
            }
        }
        output[firstIndex] = worstBranchCount;
    }
    return 0;
}
